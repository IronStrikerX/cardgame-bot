import discord
from discord.ext import commands
import random
import os
from dotenv import load_dotenv

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True
intents.dm_messages = True

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

def create_deck(include_jokers=True):
    deck = [f"{rank}{suit}" for rank in ranks for suit in suit_map.values()]
    if include_jokers:
        deck += jokers
    random.shuffle(deck)
    return deck

def format_hand(hand):
    def card_sort_key(card):
        order = ranks + jokers
        val = card[:-1] if card not in jokers else card
        return order.index(val)
    return ' '.join(sorted(hand, key=card_sort_key))

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
    val = card[:-1] if card not in jokers else card
    return ranks.index(val) if val in ranks else len(ranks)

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
gongzhu_current_trick = []
gongzhu_start_player = 0
gongzhu_collected_cards = {}
gongzhu_leading_suit = None

# --- General ---
@bot.event
async def on_ready():
    print(f"✅ Bot logged in as {bot.user}")

async def send_hand(player, hand_dict):
    if player in hand_dict:
        hand = hand_dict[player]
        formatted = format_hand(hand)
        try:
            await player.send(f"Your current hand:\n{formatted}")
        except discord.Forbidden:
            pass

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

@bot.command()
async def pl(ctx, *cards):
    global landlord_turn_index, landlord_last_play, landlord_hands, landlord_passed_players, landlord_last_player, landlord_active

    player = ctx.author
    if not landlord_active or player != landlord_players[landlord_turn_index]:
        return

    parsed = parse_cards(cards)
    if parsed is None:
        await ctx.send("Invalid card format.")
        return

    hand = landlord_hands[player]
    if not all(c in hand for c in parsed):
        await ctx.send("You can't play cards you don't have.")
        return

    for c in parsed:
        hand.remove(c)

    landlord_last_play = (player, parsed)
    landlord_last_player = player
    landlord_passed_players = set()
    await ctx.send(f"{player.display_name} played: {' '.join(parsed)}")
    await send_hand(player, landlord_hands)

    if not hand:
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

    if len([p for p in landlord_players if p != landlord_last_player and p in landlord_passed_players]) == len(landlord_players) - 1:
        landlord_last_play = None
        landlord_passed_players = set()
        await ctx.send("Everyone else passed. You may play anything.")

    landlord_turn_index = (landlord_turn_index + 1) % len(landlord_players)
    await ctx.send(f"It's now {landlord_players[landlord_turn_index].mention}'s turn.")

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

@bot.command()
async def pg(ctx, card: str):
    global gongzhu_current_trick, gongzhu_turn_index, gongzhu_start_player, gongzhu_leading_suit, gongzhu_active

    if not gongzhu_active:
        return

    player = ctx.author
    if player != gongzhu_players[gongzhu_turn_index]:
        return

    parsed = parse_cards([card])
    if parsed is None or parsed[0] not in gongzhu_hands[player]:
        await ctx.send("Invalid or unowned card.")
        return

    selected = parsed[0]
    gongzhu_hands[player].remove(selected)
    await send_hand(player, gongzhu_hands)
    gongzhu_current_trick.append((player, selected))
    await ctx.send(f"{player.display_name} played: {selected}")

    if len(gongzhu_current_trick) == 1:
        gongzhu_leading_suit = selected[-1]

    gongzhu_turn_index = (gongzhu_turn_index + 1) % len(gongzhu_players)

    if len(gongzhu_current_trick) == len(gongzhu_players):
        valid_plays = [(p, c) for p, c in gongzhu_current_trick if c[-1] == gongzhu_leading_suit]
        winner = max(valid_plays, key=lambda x: get_card_value(x[1]))[0]
        cards_taken = [c for _, c in gongzhu_current_trick]
        gongzhu_collected_cards[winner].extend(cards_taken)
        await ctx.send(f"{winner.display_name} wins the round and collects: {' '.join(cards_taken)}")

        # Reset trick
        gongzhu_current_trick = []
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

bot.run(TOKEN)
