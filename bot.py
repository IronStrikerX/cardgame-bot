import discord
from discord.ext import commands
from discord import app_commands
import random
import os
from dotenv import load_dotenv

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True
intents.dm_messages = True
intents.guild_messages = True

bot = commands.Bot(command_prefix='!', intents=intents)
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# --- Card utilities ---
suit_map = {
    'd': '♦',  # Diamonds
    'h': '♥',  # Hearts
    'c': '♣',  # Clubs
    's': '♠',  # Spades
}

ranks = ['3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A', '2']
jokers = ['Black Joker', 'Red Joker']

# ----------------------




# --- card creations ---

def create_deck(include_jokers=True):
    deck = [f"{rank}{suit}" for rank in ranks for suit in suit_map.values()]
    if include_jokers:
        deck += jokers
    random.shuffle(deck)
    return deck

def format_landlord_hand(hand):
    def card_sort_key(card):
        order = ranks + jokers
        val = card[:-1] if card not in jokers else card
        return order.index(val)
    return ' '.join(sorted(hand, key=card_sort_key))

def format_gongzhu_hand(hand):
    # Suits and ranks in desired order
    suit_order = {'♠': 0, '♥': 1, '♦': 2, '♣': 3}
    rank_order = {r: i for i, r in enumerate(['4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A'])}

    # Sorting key: (suit value, rank value)
    def sort_key(card):
        rank = card[:-1]
        suit = card[-1]
        return (suit_order[suit], rank_order.get(rank, -1))  # default -1 for unexpected ranks

    sorted_hand = sorted(hand, key=sort_key)
    return ' '.join(sorted_hand)


def parse_cards(input_cards):
    parsed = []
    for c in input_cards:
        c = c.strip()
        if c.upper() == 'BJ':
            parsed.append('Black Joker')
        elif c.upper() == 'RJ':
            parsed.append('Red Joker')
        else:
            if len(c) < 2:
                return None
            rank = c[:-1]
            suit_code = c[-1].lower()
            if rank not in ranks or suit_code not in suit_map:
                return None
            parsed.append(f"{rank}{suit_map[suit_code]}")
    return parsed

def get_card_value(card):
    rank_order = {'2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7,
                  '8': 8, '9': 9, '10': 10, 'J': 11, 'Q': 12, 'K': 13, 'A': 14}
    
    rank = card[:-1]  # removes the suite 5s => 5
    return rank_order[rank]

# --------------------------






# --- Globals for Landlord ---
landlord_players = []
landlord_active = False
landlord_hands = {}
landlord_turn_index = 0
landlord_last_play = None
landlord_extra_cards = []
landlord_last_player = None
landlord_passed_players = set()

# --- Globals for Gongzhu ---
gongzhu_players = []
gongzhu_active = False
gongzhu_hands = {}
gongzhu_turn_index = 0
gongzhu_current_round = []
gongzhu_start_player = 0
gongzhu_collected_cards = {}
gongzhu_leading_suit = None

# --- Globals for Blind Man's Bluff ---
bmb_players = []
bmb_active = False
ip_hands = {}
bmb_turn_index = 0
bmb_pot = 0
bmb_bet = 1  # Default bet is 1 chip
bmb_chips = {}
bmb_current_cards = {}
bmb_last_bettor = None


# --- General ---
@bot.event
async def on_ready():
    print(f"✅ Bot logged in as {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(e)

async def send_hand(player, hands):
    hand = hands[player]
    if gongzhu_active:
        hand_text = format_gongzhu_hand(hand)
    else:
        hand_text = format_landlord_hand(hand)
    try:
        await player.send(f"Your current hand:\n{hand_text}")
    except discord.Forbidden:
        await player.guild.system_channel.send(f"Couldn't DM {player.display_name}.")

@bot.hybrid_command(name="hand", description="Show your current hand in the active game") 
async def hand(ctx):
    player = ctx.author
    
    # Check if in Landlord game
    if landlord_active and player in landlord_hands:
        hand_text = format_landlord_hand(landlord_hands[player])
        await ctx.send(f"Your hand:\n{hand_text}", ephemeral=True)
        return
    
    # Check if in Gongzhu game
    if gongzhu_active and player in gongzhu_hands:
        hand_text = format_gongzhu_hand(gongzhu_hands[player])
        await ctx.send(f"Your hand:\n{hand_text}", ephemeral=True)
        return
    
    await ctx.send("You're not currently in an active game.", ephemeral=True)
# --------------------------------------------




# --- Landlord Game Commands ---
@bot.command()
async def startLandlord(ctx, *mentions: discord.Member):
    global landlord_active, landlord_hands, landlord_turn_index, landlord_last_play, landlord_players, landlord_extra_cards, landlord_passed_players
    if landlord_active:
        await ctx.send("A Landlord game is already in progress.")
        return
    if len(mentions) < 3 or len(mentions) > 5:
        await ctx.send("You must mention between 3 to 5 players.")
        return

    landlord_players = list(mentions)
    landlord_active = True
    deck = create_deck()
    cards_per = len(deck) // len(landlord_players)
    landlord_extra_cards = deck[cards_per * len(landlord_players):]
    hands = [deck[i * cards_per:(i + 1) * cards_per] for i in range(len(landlord_players))]

    for i, p in enumerate(landlord_players):
        landlord_hands[p] = hands[i]
        await send_hand(p, landlord_hands)

    landlord_turn_index = 0
    landlord_last_play = None
    landlord_passed_players = set()
    await ctx.send(f"Landlord game started with {len(landlord_players)} players. {landlord_players[0].mention}, it's your turn.")

@bot.hybrid_command(name="pl", description="Play cards in Landlord game")
@app_commands.describe(cards="Cards to play ('Ad = A♦, 2s = 2♠' or '3 3')")
async def pl(ctx, *, cards: str):
    global landlord_turn_index, landlord_last_play, landlord_hands, landlord_passed_players, landlord_last_player, landlord_active

    player = ctx.author
    if not landlord_active or player != landlord_players[landlord_turn_index]:
        await ctx.send("It's not your turn or no active Landlord game.", ephemeral=True)
        return

    card_list = cards.split()
    hand = landlord_hands[player].copy() 

    # Case 1: same rank (3 3 or 6 6 6)
    if all(card in ranks for card in card_list):
        parsed = []
        temp_hand = hand.copy() 
        
        for rank in card_list:
            matching_cards = [c for c in temp_hand if c.startswith(rank)]
            if not matching_cards:
                await ctx.send(f"You don't have enough {rank}s to play.", ephemeral=True)
                return
            chosen_card = matching_cards[0]
            parsed.append(chosen_card)
            temp_hand.remove(chosen_card)
    else:

        parsed = parse_cards(card_list)
        if parsed is None:
            await ctx.send("Invalid card format.", ephemeral=True)
            return
        temp_hand = hand.copy()
        for card in parsed:
            if card not in temp_hand:
                await ctx.send(f"You don't have {card} in your hand.", ephemeral=True)
                return
            temp_hand.remove(card)

    # modify the actual hand
    for card in parsed:
        landlord_hands[player].remove(card)

    landlord_last_play = (player, parsed)
    landlord_last_player = player
    landlord_passed_players = set()
    
    await ctx.send(f"{player.display_name} played: {' '.join(parsed)}")
    await ctx.send(f"You played: {' '.join(parsed)}\nYour remaining hand:\n{format_landlord_hand(landlord_hands[player])}", ephemeral=True)
    await send_hand(player, landlord_hands)

    if not landlord_hands[player]:
        await ctx.send(f"{player.display_name} wins the Landlord game!")
        landlord_active = False
        return

    landlord_turn_index = (landlord_turn_index + 1) % len(landlord_players)
    await ctx.send(f"It's now {landlord_players[landlord_turn_index].mention}'s turn.")

@bot.command()
async def xl(ctx):
    global landlord_passed_players, landlord_turn_index, landlord_last_play, landlord_last_player

    player = ctx.author
    if not landlord_active or player != landlord_players[landlord_turn_index]:
        return

    landlord_passed_players.add(player)
    await ctx.send(f"{player.display_name} passed.")

    # Check if all but last player have passed
    if len([p for p in landlord_players if p != landlord_last_player and p in landlord_passed_players]) == len(landlord_players) - 1:
        landlord_last_play = None
        landlord_passed_players = set()
        await ctx.send("Everyone else passed. You may play anything.")
        landlord_turn_index = landlord_players.index(landlord_last_player)
        await ctx.send(f"It's now {landlord_players[landlord_turn_index].mention}'s turn.")
    else:
        landlord_turn_index = (landlord_turn_index + 1) % len(landlord_players)
        await ctx.send(f"It's now {landlord_players[landlord_turn_index].mention}'s turn.")
# -------------------------------------------




# --- Gongzhu Game Commands ---
@bot.command()
async def startGongzhu(ctx, *mentions: discord.Member):
    global gongzhu_active, gongzhu_players, gongzhu_hands, gongzhu_turn_index, gongzhu_start_player, gongzhu_collected_cards

    if gongzhu_active:
        await ctx.send("A Gongzhu game is already in progress.")
        return

    if not (3 <= len(mentions) <= 5):
        await ctx.send("Gongzhu must be played with 3-5 players.")
        return

    gongzhu_players = list(mentions)
    gongzhu_active = True
    deck = [f"{rank}{suit}" for rank in ranks if rank not in ('2', '3') for suit in suit_map.values()]
    random.shuffle(deck)
    per_player = len(deck) // len(gongzhu_players)
    hands = [deck[i * per_player:(i + 1) * per_player] for i in range(len(gongzhu_players))]

    gongzhu_hands = {}
    gongzhu_collected_cards = {p: [] for p in gongzhu_players}

    for i, p in enumerate(gongzhu_players):
        gongzhu_hands[p] = hands[i]
        await send_hand(p, gongzhu_hands)

    gongzhu_turn_index = 0
    gongzhu_start_player = 0
    await ctx.send(f"Gongzhu started with {len(gongzhu_players)} players. {gongzhu_players[0].mention} plays first.")

@bot.hybrid_command(name="pg", description="Play a card in Gongzhu game")
@app_commands.describe(card="Card to play (e.g., 'A♦' or 'RJ' for Red Joker)")
async def pg(ctx, *, card: str):
    global gongzhu_current_round, gongzhu_turn_index, gongzhu_start_player, gongzhu_leading_suit, gongzhu_active

    if not gongzhu_active:
        await ctx.send("No active Gongzhu game.", ephemeral=True)
        return

    player = ctx.author
    if player != gongzhu_players[gongzhu_turn_index]:
        await ctx.send("It's not your turn.", ephemeral=True)
        return

    parsed = parse_cards([card])
    if parsed is None or parsed[0] not in gongzhu_hands[player]:
        await ctx.send("Invalid or unowned card.", ephemeral=True)
        return

    selected = parsed[0]
    gongzhu_hands[player].remove(selected)
    
    await ctx.send(f"{player.display_name} played: {selected}")
    

    remaining_hand = format_gongzhu_hand(gongzhu_hands[player])
    await ctx.send(f"You played: {selected}\nYour remaining hand:\n{remaining_hand}", ephemeral=True)
    

    await send_hand(player, gongzhu_hands)

    gongzhu_current_round.append((player, selected))
    if len(gongzhu_current_round) == 1:
        gongzhu_leading_suit = selected[-1]

    gongzhu_turn_index = (gongzhu_turn_index + 1) % len(gongzhu_players)

    if len(gongzhu_current_round) == len(gongzhu_players):
        valid_plays = [(p, c) for p, c in gongzhu_current_round if c[-1] == gongzhu_leading_suit]
        winner = max(valid_plays, key=lambda x: get_card_value(x[1]))[0]
        cards_taken = [c for _, c in gongzhu_current_round]
        gongzhu_collected_cards[winner].extend(cards_taken)
        await ctx.send(f"{winner.display_name} wins the round and collects: {' '.join(cards_taken)}")

        # Reset round
        gongzhu_current_round = []
        gongzhu_leading_suit = None
        gongzhu_turn_index = gongzhu_players.index(winner)

        # End condition
        if all(len(gongzhu_hands[p]) == 0 for p in gongzhu_players):
            gongzhu_active = False
            await ctx.send("Gongzhu game over. Cards collected:")
            for p in gongzhu_players:
                collected = gongzhu_collected_cards[p]
                penalty = [c for c in collected if c.endswith('♥') or c in ["10♣", "J♦", "Q♠"]]
                await ctx.send(f"{p.display_name}: {', '.join(penalty) if penalty else 'No penalty cards.'}")
            return

        await ctx.send(f"Next round starts. {winner.mention} plays first.")
    else:
        await ctx.send(f"{gongzhu_players[gongzhu_turn_index].mention}, it's your turn.")
# ----------------------------------



# --- BMB Commands ---
@bot.command(name="startBMB")
async def start_ip(ctx, p1: discord.Member, p2: discord.Member):
    global bmb_players, bmb_active, bmb_turn_index, bmb_pot, bmb_price
    global bmb_chips, bmb_current_cards, bmb_bets, bmb_last_raiser, BMB_ANTE

    BMB_ANTE = 5 

    if bmb_active:
        await ctx.send("A BMB game is already in progress.")
        return

    bmb_players = [p1, p2]
    bmb_chips = {p1: 100, p2: 100}
    bmb_active = True
    bmb_turn_index = 0
    bmb_pot = 0
    bmb_price = 0
    bmb_current_cards = {}
    bmb_bets = {p1: 0, p2: 0}
    bmb_last_raiser = None

    # Apply ante
    for player in bmb_players:
        bmb_chips[player] -= BMB_ANTE
        bmb_pot += BMB_ANTE
        bmb_bets[player] = BMB_ANTE

    await deal_bmb_cards()
    await ctx.send(
        f"Blind Man's Bluff started between {p1.mention} and {p2.mention}!\n"
        f"Each player antes {BMB_ANTE} chip(s).\n"
        f"Pot: {bmb_pot}.\n"
        f"{bmb_players[0].mention}, it's your turn! Use `!raise`, `!call`, or `!fold`."
    )

async def deal_bmb_cards():
    global bmb_current_cards
    deck = create_deck(include_jokers=False)
    p1_card = random.choice(deck)
    deck.remove(p1_card)
    p2_card = random.choice(deck)

    bmb_current_cards[bmb_players[0]] = p1_card
    bmb_current_cards[bmb_players[1]] = p2_card

    try:
        await bmb_players[0].send(f"The other player is showing: {p2_card}")
        await bmb_players[1].send(f"The other player is showing: {p1_card}")
    except discord.Forbidden:
        pass

@bot.command(name="raise")
async def bmb_raise_cmd(ctx, amount: int = 1):
    global bmb_turn_index, bmb_pot, bmb_price, bmb_last_raiser, bmb_bets

    player = ctx.author
    if not bmb_active or player != bmb_players[bmb_turn_index]:
        return
    
    if to_call < BMB_ANTE:
        await ctx.send(f"{player.mention}, you have to raise more than the ante which is at: {BMB_ANTE}.")
        return

    opponent = bmb_players[1 - bmb_turn_index]
    to_call = bmb_bets[opponent] - bmb_bets[player]

    total_required = to_call + amount
    if bmb_chips[player] < total_required:
        await ctx.send(f"{player.mention}, you need {total_required} chips to call and raise, but only have {bmb_chips[player]}.")
        return

    bmb_chips[player] -= total_required
    bmb_bets[player] += total_required
    bmb_pot += total_required
    bmb_price = bmb_bets[player] - bmb_bets[opponent]
    bmb_last_raiser = player

    await ctx.send(
        f"{player.display_name} raises {amount} chips (calls {to_call}, raises {amount}).\n"
        f"Current price to call: {bmb_price}.\nPot: {bmb_pot}.\n"
        f"{opponent.mention}, your move!"
    )

    bmb_turn_index = 1 - bmb_turn_index

@bot.command(name="call")
async def bmb_call_cmd(ctx):
    global bmb_turn_index, bmb_pot, bmb_active, bmb_price, bmb_bets, bmb_last_raiser

    player = ctx.author
    if not bmb_active or player != bmb_players[bmb_turn_index]:
        return

    opponent = bmb_players[1 - bmb_turn_index]
    to_call = bmb_bets[opponent] - bmb_bets[player]

    if to_call == 0:
        # Nothing to call. treat as a check and pass turn
        await ctx.send(f"{player.display_name} checks.\n{opponent.mention}, your move!")
        bmb_turn_index = 1 - bmb_turn_index
        return

    call_amount = min(bmb_chips[player], to_call)
    bmb_chips[player] -= call_amount
    bmb_bets[player] += call_amount
    bmb_pot += call_amount


    p1, p2 = bmb_players
    card1 = bmb_current_cards[p1]
    card2 = bmb_current_cards[p2]

    await ctx.send(f"{p1.display_name} had: {card1}\n{p2.display_name} had: {card2}")

    val1 = get_card_value(card1)
    val2 = get_card_value(card2)

    if val1 > val2:
        winner = p1
    elif val2 > val1:
        winner = p2
    else:
        winner = None

    if winner:
        if bmb_bets[player] < bmb_bets[opponent] and winner == player:
            win_amount = bmb_bets[player] + (bmb_pot - bmb_bets[player] - bmb_bets[opponent])
            await ctx.send(f"{winner.display_name} wins but didn't match the full raise — they win only {win_amount} chips.")
            bmb_chips[winner] += win_amount
            bmb_chips[opponent] += bmb_pot - win_amount
        else:
            bmb_chips[winner] += bmb_pot
            await ctx.send(f"{winner.display_name} wins the round and takes {bmb_pot} chips!")
    else:
        await ctx.send("It's a tie. Pot is split.")
        bmb_chips[p1] += bmb_pot // 2
        bmb_chips[p2] += bmb_pot - (bmb_pot // 2)

    bmb_pot = 0
    await display_chip_counts(ctx)

    if bmb_chips[p1] <= 0:
        await ctx.send(f"{p1.display_name} is out of chips. {p2.display_name} wins the game!")
        bmb_active = False
    elif bmb_chips[p2] <= 0:
        await ctx.send(f"{p2.display_name} is out of chips. {p1.display_name} wins the game!")
        bmb_active = False
    else:
        await start_new_bmb_round(ctx)



async def start_new_bmb_round(ctx):
    global bmb_turn_index, bmb_pot, bmb_price, bmb_bets, bmb_current_cards, bmb_last_raiser

    bmb_turn_index = 0
    bmb_pot = 0
    bmb_price = 0
    bmb_bets = {bmb_players[0]: 0, bmb_players[1]: 0}
    bmb_last_raiser = None

    for player in bmb_players:
        if bmb_chips[player] > 0:
            bmb_chips[player] -= BMB_ANTE
            bmb_pot += BMB_ANTE
            bmb_bets[player] = BMB_ANTE

    await deal_bmb_cards()
    await ctx.send(f"New round begins! Each player antes {BMB_ANTE} chip(s).\nPot: {bmb_pot}.\n{bmb_players[0].mention}, it's your turn! Use `!raise`, `!call`, or `!fold`.")

@bot.command(name="fold")
async def bmb_fold_cmd(ctx):
    global bmb_turn_index, bmb_active, bmb_pot

    player = ctx.author
    if not bmb_active or player != bmb_players[bmb_turn_index]:
        return

    winner = bmb_players[1 - bmb_turn_index]
    bmb_chips[winner] += bmb_pot
    await ctx.send(f"{player.display_name} folded. {winner.display_name} wins {bmb_pot} chips!")

    await display_chip_counts(ctx)

    if bmb_chips[player] <= 0:
        await ctx.send(f"{player.display_name} is out of chips. {winner.display_name} wins the game!")
        bmb_active = False
        return

    await start_new_bmb_round(ctx)

async def display_chip_counts(ctx):
    p1, p2 = bmb_players
    await ctx.send(f"Chips now:\n{p1.display_name}: {bmb_chips[p1]}\n{p2.display_name}: {bmb_chips[p2]}")

# ---------------------------------




# --- Global Commands ---

@bot.command()
async def endgame(ctx):
    global landlord_active, landlord_players, landlord_hands, landlord_turn_index, landlord_last_play, landlord_extra_cards, landlord_last_player, landlord_passed_players
    global gongzhu_active, gongzhu_players, gongzhu_hands, gongzhu_turn_index, gongzhu_current_round, gongzhu_start_player, gongzhu_collected_cards, gongzhu_leading_suit
    global bmb_players, bmb_active, bmb_turn_index, bmb_pot, bmb_bet, bmb_chips, bmb_current_cards, bmb_last_bettor, ip_hands

    # Reset BMB variables
    bmb_players = []
    bmb_active = False
    ip_hands = {}
    bmb_turn_index = 0
    bmb_pot = 0
    bmb_bet = 1
    bmb_chips = {}
    bmb_current_cards = {}
    bmb_last_bettor = None

    # Reset Landlord variables
    landlord_active = False
    landlord_players = []
    landlord_hands = {}
    landlord_turn_index = 0
    landlord_last_play = None
    landlord_extra_cards = []
    landlord_last_player = None
    landlord_passed_players = set()

    # Reset Gongzhu variables
    gongzhu_active = False
    gongzhu_players = []
    gongzhu_hands = {}
    gongzhu_turn_index = 0
    gongzhu_current_round = []
    gongzhu_start_player = 0
    gongzhu_collected_cards = {}
    gongzhu_leading_suit = None

    await ctx.send("All Games have been ended.")


bot.run(TOKEN)
