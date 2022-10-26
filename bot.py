# import os
import discord
import random
import re
from discord.ext import commands


BOT_PREFIX = '!'
TOKEN = 'BOT_TOKEN'
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix=BOT_PREFIX, intents=intents, help_command=None)


# TODO win streak - integracao com twitch?
# TODO estatisticas (longest winstreak, maior numero de vitorias, lista de quem cada jogador venceu)   DONE
# TODO avisar quando jogador fez volta inteira na fila   DONE BUT NOT TESTED
# TODO limite de rodadas por evento?
# TODO caixa de bombom
# TODO blacklist
# TODO vidas pra cada jogador


byeMsg = ["correu que nem um franguinho", "picou a mula da fila", "se teleportou pra fora da fila",
          "saiu pra ver o mamaco", "tirou o cavalinho da fila", "chamou o CervoTaxi e se mandou da fila",
          "foi macetar em outro lugar"]


# -- QUEUE SETTINGS --

class QueueConfigs:
    def __init__(self):
        self.ft_config = "default"  # If num of players <= 4, will be ft3. Else, will be ft2
        self.max_wins = 3  # Number of times a player can claim win, after that, it's retired from the next match
        self.lobby_id = None  # CCCaster/Concerto Lobby ID
        self.keyword = "Teste"  # Lumina Room Keyword

    async def set_config(self, context, argument):
        self.ft_config = "FT" + argument
        print(f'Agora é {self.ft_config} nessa bagaça')

    async def id_config(self, context, argument):
        if argument == "none":
            self.lobby_id = None
        else:
            self.lobby_id = int(argument)
            print(f'Novo Lobby ID é {self.lobby_id}')
        await QUEUE.show_queue(context)

    async def keyword_config(self, context, argument):
        if argument == "none":
            self.keyword = None
        else:
            self.keyword = argument
            print(f'Nova Keyword é {self.keyword}')
        await QUEUE.show_queue(context)

    async def wins_config(self, context, argument):
        if argument == "none":
            self.max_wins = None
            print('Limite de ggez desativado')
        else:
            self.max_wins = int(argument)
            print(f'Limite de ggez configurado para {self.max_wins}')
        await QUEUE.show_queue(context)


CONFIGS = QueueConfigs()


class QManager:
    def __init__(self):
        self.queue = []
        self.last_winner = None
        self.last_loser = None
        self.win_count = 0
        self.new_match = False
        # self.maxRounds = 0
        self.playerIpList = {}

        self.message = None  # Contains the queue display message
        self.call = None  # Contains the match calls message

        # statistics
        self.victimList = {}
        self.winLog = []
        self.queue_stats = {}
        self.longest_win_streak = ["", 1]

    # -- DATA HANDLING FUNCTIONS --

    async def add_player(self, interaction):
        member = interaction.user
        context = interaction.channel
        if member in self.queue:
            await interaction.response.send_message(f'Você já esta na fila na posição {self.queue.index(member) + 1}',
                                                    ephemeral=True)
        else:
            self.queue.append(member)

            if member not in self.queue_stats:
                self.queue_stats[member] = [0, 0, []]
            await interaction.response.send_message('Você entrou na fila', ephemeral=True)
            if self.number_of_players() == 2:
                self.new_match = True
                await self.show_queue(context)
                await self.call_next_match(context)
            elif self.active_queue():
                await self.show_queue(context)
            else:
                await self.show_queue(context)

    async def remove_player(self, interaction):
        member = interaction.user
        context = interaction.channel
        if member not in self.queue:
            await interaction.response.send_message('Você não está na fila', ephemeral=True)
        else:
            player_pos = self.queue.index(member)
            self.queue.remove(member)
            if player_pos < 2 and self.number_of_players() > 1:
                self.new_match = True
                await self.call_next_match(context)
            await interaction.response.send_message(f'Você {random.choices(byeMsg)[0]}', ephemeral=True)
            await self.show_queue(context)

    async def skip_turn(self, interaction):
        member = interaction.user
        context = interaction.channel
        if member not in self.queue or not self.active_queue():
            await interaction.response.send_message('Não', ephemeral=True)
        elif member in self.first_players():
            if member == self.last_winner:
                self.win_count = 0
            self.queue.remove(member)
            self.queue.append(member)

            await interaction.response.send_message('Você foi pro fim da fila')
            self.new_match = True
            await self.show_queue(context)
            await self.call_next_match(context)

    async def force_skip(self, context):
        member = context.message.mentions.pop(0)
        if member not in self.queue or not self.active_queue():
            await context.send(f'Não')
        elif member in self.first_players():
            if member == self.last_winner:
                self.win_count = 0
            self.queue.remove(member)
            self.queue.append(member)

            self.new_match = True
            await self.show_queue(context)
            await self.call_next_match(context)
            await context.send(f'*{member.name} foi pro fim da fila*')

    async def force_remove(self, context):
        member = context.message.mentions[0]
        if member in self.queue:
            self.queue.remove(member)
            await self.show_queue(context)
            await context.send(f'*{member.name} foi removido da fila*')
        else:
            print(f'Usuario não consta na fila')

    async def resolve_match(self, interaction):
        context = interaction.channel

        if self.active_queue():
            winner = interaction.user

            if winner in self.first_players():
                if winner == self.last_winner:
                    self.win_count += 1
                else:
                    self.win_count = 1

                self.last_winner = winner
                pos = self.queue.index(winner)

                if pos == 1:  # winner is second in line
                    loser = self.queue.pop(0)
                    result = f'{winner.name}(W) x {loser.name}(L)'
                else:  # winner is first in line
                    loser = self.queue.pop(1)
                    result = f'{loser.name}(L) x {winner.name}(W)'

                self.last_loser = loser
                self.queue.append(loser)

                if self.win_count == CONFIGS.max_wins:
                    winner = self.queue.pop(0)
                    self.queue.append(winner)
                    self.win_count = 0

                for name in self.queue_stats[winner][2]:
                    if loser == name and CONFIGS.max_wins is None:
                        await interaction.response.send_message(f'*Jogador {winner} deu a volta na fila*')

                # statistics --------------------------------------
                self.queue_stats[winner][0] += 1
                self.queue_stats[loser][1] += 1
                self.queue_stats[winner][2].append(loser.name)
                self.winLog.append(result)

                if CONFIGS.max_wins is None and self.win_count > self.longest_win_streak[1]:
                    self.longest_win_streak[0] = self.last_winner.name
                    self.longest_win_streak[1] = self.win_count
                # -------------------------------------------------

                self.new_match = True
                await self.show_queue(context)
                await self.call_next_match(context)

            else:
                await interaction.response.send_message('Não mente, rapaz!', ephemeral=True)
        else:
            await interaction.response.send_message('Esse comando só vai funcionar a partir de 3 players',
                                                    ephemeral=True)

    async def show_queue(self, context):
        buttons = ButtonsQueue(timeout=None)
        buttons.add_item(self.button_join())

        if self.message is None:
            self.message = await context.send(content=TEXTS.display(0), view=buttons)
        else:
            if self.active_queue():
                if self.new_match is True:
                    await self.message.delete()
                    self.message = await context.send(content=TEXTS.display(3), view=buttons)
                else:
                    await self.message.edit(content=TEXTS.display(3), view=buttons)
            elif self.number_of_players() == 2:
                await self.message.edit(content=TEXTS.display(2), view=buttons)
            elif self.number_of_players() == 1:
                await self.message.edit(content=TEXTS.display(1), view=buttons)
            elif self.number_of_players() == 0:
                await self.message.edit(content=TEXTS.display(0), view=buttons)

    @staticmethod
    def button_join():
        if CONFIGS.lobby_id is None:
            return discord.ui.Button(label='Entrar no lobby', style=discord.ButtonStyle.link, disabled=True,
                                     url=f'https://invite.meltyblood.club/{CONFIGS.lobby_id}')
        else:
            return discord.ui.Button(label='Entrar no lobby', style=discord.ButtonStyle.link,
                                     url=f'https://invite.meltyblood.club/{CONFIGS.lobby_id}')

    def reset(self):
        pass  # TODO resetar dados

    async def call_next_match(self, context):
        buttons = ButtonsMatch(timeout=None)
        if self.active_queue():
            if self.last_winner is None and self.new_match is True:
                self.call = await context.send(TEXTS.match(), view=buttons)
            elif self.get_player_ip(self.queue[0]) != "" or self.get_player_ip(self.queue[1]) != "" or \
                    self.new_match is True:
                await self.call.edit(content=TEXTS.match(), view=buttons)
            else:
                await self.call.delete()
                self.call = await context.send(TEXTS.match(), view=buttons)
            self.new_match = False
        else:
            if self.last_winner is None and self.new_match is True:
                self.call = await context.send(TEXTS.match())
            elif self.get_player_ip(self.queue[0]) != "" or self.get_player_ip(self.queue[1]) != "" or \
                    self.new_match is True:
                await self.call.edit(content=TEXTS.match())
            else:
                await self.call.delete()
                await self.call.edit(content=TEXTS.match())
            self.new_match = False

    async def revert(self):
        if self.last_winner is not None:
            self.queue_stats[self.last_winner][0] -= 1
            self.queue_stats[self.last_loser][1] -= 1
            self.queue_stats[self.last_winner][2].pop()
            self.winLog.pop()
            if self.last_winner.name == self.longest_win_streak[0]:
                self.longest_win_streak[1] -= 1
            member = self.queue.pop()
            self.queue.insert(1, member)

    def rule_set(self):
        if CONFIGS.ft_config == "default":
            if len(self.queue) > 4:
                return "FT2"
            else:
                return "FT3"
        else:
            return CONFIGS.ft_config

    def first_players(self):
        return self.queue[0:2]

    def number_of_players(self):
        return len(self.queue)

    def active_queue(self):
        return len(self.queue) > 2

    def add_player_ip(self, member, ip):
        self.playerIpList[member] = ip

    def get_player_ip(self, member):
        ip = self.playerIpList.get(member)
        if ip is not None:
            return ip
        else:
            return ""


QUEUE = QManager()


# -- QUEUE MESSAGES TEXTS --

class QueueText:
    @staticmethod
    def display(option):
        if CONFIGS.lobby_id is None and CONFIGS.keyword is None:
            title = f'> **Open Lobby**'
        elif CONFIGS.lobby_id is None and CONFIGS.keyword is not None:
            title = f'> **Open Lobby: kw {CONFIGS.keyword}**'
        else:
            title = f'> **Open Lobby: ID {CONFIGS.lobby_id}**'

        if option == 0:
            return (
                title +
                f"\n > A fila está vazia. Entre na fila se for brabo"
            )
        elif option == 1:
            return (
                title +
                f'\n > {QUEUE.queue[0].name} está esperando desafiantes \n'
            )
        elif option == 2:
            return (
                title +
                f'\n > {QUEUE.queue[0].name} x {QUEUE.queue[1].name} \n'
                f'> Fila: '
            )
        elif option == 3:
            if CONFIGS.max_wins is not None:
                title += f' / {QUEUE.win_count} de {CONFIGS.max_wins} ggez'

            if QUEUE.last_winner is None:
                stat = ""
            elif CONFIGS.max_wins is None:
                stat = f'Maior maceteiro: {TEXTS.player_more_wins()} / Maior vítima: {TEXTS.player_more_losses()} \n'
                if QUEUE.longest_win_streak[1] > 1:
                    stat += f'Maior sequência: {QUEUE.longest_win_streak[1]} vitórias ({QUEUE.longest_win_streak[0]})'
            else:
                stat = f'Maior maceteiro: {TEXTS.player_more_wins()}'

            return (
                title +
                f'\n > {QUEUE.queue[0].name} x {QUEUE.queue[1].name} \n'
                f'> Fila: {", ".join([member.name for member in QUEUE.queue[2:]])} \n'
                + stat
            )

    @staticmethod
    def player_more_wins():
        maximum = 0
        player = ""
        for member in QUEUE.queue_stats:
            if QUEUE.queue_stats[member][0] > maximum:
                maximum = QUEUE.queue_stats[member][0]
                player = member
        if player != "":
            return f'{player.name} ({maximum} wins)'
        else:
            return player

    @staticmethod
    def player_more_losses():
        maximum = 0
        player = ""
        for member in QUEUE.queue_stats:
            if QUEUE.queue_stats[member][1] > maximum:
                maximum = QUEUE.queue_stats[member][1]
                player = member
        if player != "":
            return f'{player.name} ({maximum} losses)'
        else:
            return player

    @staticmethod
    def match():
        return (f'Próxima partida: {QUEUE.queue[0].mention} [{QUEUE.get_player_ip(QUEUE.queue[0])}]'
                f' vs '
                f'{QUEUE.queue[1].mention} [{QUEUE.get_player_ip(QUEUE.queue[1])}]'
                f' - {QUEUE.rule_set()}')

    @staticmethod
    async def show_stats(interaction):
        member = interaction.user
        if member in QUEUE.queue:
            text = f"**{member.name}** \n"\
                   f"{QUEUE.queue_stats[member][0]} vitórias / {QUEUE.queue_stats[member][1]} derrotas \n"\
                   f"Vitimados: {', '.join([name for name in QUEUE.queue_stats[member][2]])}"
            await interaction.response.send_message(text, ephemeral=True)
        else:
            await interaction.response.send_message('Você não está na fila', ephemeral=True)

    @staticmethod
    async def show_win_log(context):
        await context.send(f"*{' ; '.join(QUEUE.winLog)}*")


TEXTS = QueueText()


# -- BUTTONS --

class ButtonsQueue(discord.ui.View):
    @discord.ui.button(label="Entrar na fila", style=discord.ButtonStyle.red)
    async def btn_enter(self, interaction: discord.Interaction, button: discord.ui.button):
        await QUEUE.add_player(interaction)

    @discord.ui.button(label="Sair", style=discord.ButtonStyle.gray)
    async def btn_exit(self, interaction: discord.Interaction, button: discord.ui.button):
        await QUEUE.remove_player(interaction)

    @discord.ui.button(label="Stats", style=discord.ButtonStyle.gray)
    async def btn_stats(self, interaction: discord.Interaction, button: discord.ui.button):
        await TEXTS.show_stats(interaction)


class ButtonsMatch(discord.ui.View):
    @discord.ui.button(label="GGEZ", style=discord.ButtonStyle.primary)
    async def btn_ggez(self, interaction: discord.Interaction, button: discord.ui.button):
        await QUEUE.resolve_match(interaction)

    @discord.ui.button(label="Pular", style=discord.ButtonStyle.gray)
    async def btn_skip(self, interaction: discord.Interaction, button: discord.ui.button):
        await QUEUE.skip_turn(interaction)


# -- CUSTOM CHECKER --

def is_channel(channel_name):
    def predicate(ctx):
        return ctx.message.channel.name == channel_name
    return commands.check(predicate)


# -- BOT EVENTS --

@bot.event
async def on_ready():
    print('Logged in as')
    print(bot.user.name)
    print(bot.user.id)
    print('------')
    await bot.change_presence(status=discord.Status.online, activity=discord.Game(name="!comandos"))


@bot.event
async def on_message(message):
    test = re.match("\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\:\d{1,5}", message.content)
    if test is not None:
        if message.channel.name == "Open lobby" and len(QUEUE.queue) != 0:
            QUEUE.add_player_ip(message.author, test.group())
            await QUEUE.call_next_match(message.channel)
    await bot.process_commands(message)


# -- BOT COMMANDS --

# @bot.command(name="ativar")
# @commands.has_role("Developer")
# async def open_queue(ctx):
#    await ctx.send("" + "Teste ativar")


# @bot.command(name="desativar")
# @commands.has_role("Developer")
# async def close_queue(ctx):
#    await ctx.send("" + "Teste desativar")


@bot.command(name="fila")  # Starts the queue
@commands.has_any_role("Developer", "Organizador")
# @is_channel("eventos")
async def show_queue(ctx):
    await QUEUE.show_queue(ctx)


@bot.command(name="winlog")
@commands.has_any_role("Developer", "Organizador")
# @is_channel("eventos")
async def show_win_log(ctx):
    await TEXTS.show_win_log(ctx)


@bot.command(name="wins")  # Send '!wins none' to deactivate the wins limit or '!wins [number]' to set other limit
@commands.has_any_role("Developer", "Organizador")
# @is_channel("eventos")
async def wins_config(ctx, arg):
    await CONFIGS.wins_config(ctx, arg)


@bot.command(name="ft")  # Send '!ft [number]' to change the set config for the next matches or !ft default
@commands.has_any_role("Developer", "Organizador")
# @is_channel("eventos")
async def set_config(ctx, arg):
    await CONFIGS.set_config(ctx, arg)


@bot.command(name="newid")  # Send '!newid [number]' to change the lobby id or '!newid none' if there isn't one
@commands.has_any_role("Developer", "Organizador")
async def new_lobby_id(ctx, arg):
    await CONFIGS.id_config(ctx, arg)


@bot.command(name="newkw")  # Send '!newkw [text]' to change the room keyword or '!newkw none' if there isn't one
@commands.has_any_role("Developer", "Organizador")
async def new_room_keyword(ctx, arg):
    await CONFIGS.keyword_config(ctx, arg)


@bot.command(name="remover")
@commands.has_any_role("Developer", "Organizador")
async def remove_from_queue(ctx):
    await QUEUE.force_remove(ctx)


@bot.command(name="chutar")
@commands.has_any_role("Developer", "Organizador")
async def force_skip(ctx):
    await QUEUE.force_skip(ctx)


@bot.command(name="reverter")
@commands.has_any_role("Developer", "Organizador")
async def revert(ctx):
    await QUEUE.revert()
    await QUEUE.call_next_match(ctx)


@bot.command(name="comandos")
async def show_commands(ctx):
    await ctx.send("" + "```!moeda , !d20, !ggez, !pular```")


@bot.command(name="moeda")
# @is_channel("eventos")
async def coin_toss(ctx):
    answer = random.choice(["cara", "coroa"])
    await ctx.send(ctx.author.mention + " jogou uma moeda e deu: " + answer)


@bot.command(name="d20")
async def d20_roll(ctx):
    answer = random.randint(1, 20)
    await ctx.send(f'{ctx.author.mention} jogou um dado e caiu: {answer}')


bot.run(TOKEN)
