import discord
from discord.ext import commands, tasks
from discord import ui, ButtonStyle
import asyncio
import time
import traceback
import re
from datetime import datetime, timedelta
import sqlite3
import random
import os

# COLE SEU TOKEN AQUI ↓
TOKEN = 'DISCORD_TOKEN'

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

# ============================
# CONFIGURAÇÕES DO SISTEMA DE ATENDIMENTO
# ============================

# IDs dos canais para atendimento
CANAL_ORIGEM_ID = 1410849795303538770
CANAIS_ATENDIMENTO_IDS = [
    1410849519649685514, 1441237528366682223, 1410802938968019004,
    1410849605536579624, 1440885224845082747, 1424228137952219248
]
CANAL_REGISTRO_ID = 1437141603939782757

# Dicionários globais para atendimento
atendimentos_ativos = {}
ultimo_atendimento = 0
RATE_LIMIT_SEGUNDOS = 5

# ============================
# CONFIGURAÇÕES DO SISTEMA DE MONITORAMENTO
# ============================

CANAL_ENTRADA_ID = 1442338546412159018
CANAL_FACCOES_ID = 1436821935978713228
CANAL_PAINEL_ID = 1443468893971808349
ATUALIZACAO_AUTOMATICA = True

# Conexão com o banco de dados
conn = sqlite3.connect('players_faccoes.db', check_same_thread=False)
cursor = conn.cursor()

# Criar tabelas
cursor.execute('''
CREATE TABLE IF NOT EXISTS faccoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT UNIQUE,
    segmento TEXT,
    cor INTEGER,
    data_criacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    data_entrega TIMESTAMP,
    recem_entregue BOOLEAN DEFAULT FALSE
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS registros_players (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    faccao_id INTEGER,
    quantidade INTEGER,
    data_hora_original TIMESTAMP,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (faccao_id) REFERENCES faccoes (id)
)
''')

conn.commit()

# ============================
# CLASSES DO SISTEMA DE ATENDIMENTO
# ============================

class MotivoModal(ui.Modal, title='Preencher Atendimento'):
    def __init__(self, view_instance):
        super().__init__()
        self.view_instance = view_instance
    
    motivo = ui.TextInput(
        label='Motivo do Atendimento',
        placeholder='Descreva detalhadamente o motivo...',
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=500
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            # Salvar informações no view
            self.view_instance.motivo_atendimento = self.motivo.value
            self.view_instance.responsavel = interaction.user
            
            # Atualizar mensagem com as informações preenchidas
            auxiliares_mentions = [f"<@{uid}>" for uid in self.view_instance.auxiliares]
            
            content = (
                f"📝 **REGISTRO DE ATENDIMENTO - PREENCHIDO**\n"
                f"**Líder Atendido:** {self.view_instance.usuario_atendido.mention}\n"
                f"**Canal de Atendimento:** {self.view_instance.canal_atendimento.mention}\n"
                f"**Responsável:** {interaction.user.mention}\n"
                f"**Auxiliares:** {', '.join(auxiliares_mentions) if auxiliares_mentions else 'Nenhum'}\n"
                f"**Motivo:** {self.motivo.value}\n\n"
                f"⚠️ **Aguardando finalização do atendimento...**"
            )
            
            await self.view_instance.mensagem_original.edit(content=content, view=self.view_instance)
            
            await interaction.response.send_message(
                "✅ Informações preenchidas! Clique em **FINALIZAR ATENDIMENTO** quando terminar.",
                ephemeral=True
            )
            
        except Exception as e:
            print(f"❌ Erro ao preencher: {e}")
            traceback.print_exc()
            await interaction.response.send_message(
                "❌ Erro ao preencher atendimento.",
                ephemeral=True
            )

class AtendimentoView(ui.View):
    def __init__(self, usuario_atendido, canal_atendimento, mensagem_original, atendimento_id):
        super().__init__(timeout=None)
        self.usuario_atendido = usuario_atendido
        self.canal_atendimento = canal_atendimento
        self.mensagem_original = mensagem_original
        self.atendimento_id = atendimento_id
        self.auxiliares = []
        self.motivo_atendimento = None
        self.responsavel = None
    
    @ui.button(label='📝 PREENCHER ATENDIMENTO', style=ButtonStyle.primary, row=0)
    async def preencher_atendimento(self, interaction: discord.Interaction, button: ui.Button):
        try:
            # Verificar se o usuário é um auxiliar
            if interaction.user.id in self.auxiliares:
                await interaction.response.send_message(
                    "❌ Você está registrado como **AUXILIAR** e não pode ser o responsável! Remova-se como auxiliar primeiro.",
                    ephemeral=True
                )
                return
            
            # Verificar se já foi preenchido por outra pessoa
            if self.responsavel and self.responsavel.id != interaction.user.id:
                await interaction.response.send_message(
                    f"⚠️ Este atendimento já foi preenchido por {self.responsavel.mention}. Apenas o responsável ou staff pode editar.",
                    ephemeral=True
                )
                return
            
            modal = MotivoModal(self)
            await interaction.response.send_modal(modal)
        except Exception as e:
            print(f"❌ Erro ao abrir modal: {e}")
            await interaction.response.send_message(
                "❌ Erro ao abrir formulário.",
                ephemeral=True
            )
    
    @ui.button(label='✅ FINALIZAR ATENDIMENTO', style=ButtonStyle.green, row=0)
    async def finalizar_atendimento(self, interaction: discord.Interaction, button: ui.Button):
        try:
            # Verificar se o atendimento foi preenchido
            if not self.motivo_atendimento or not self.responsavel:
                await interaction.response.send_message(
                    "⚠️ Você precisa **PREENCHER O ATENDIMENTO** antes de finalizar!",
                    ephemeral=True
                )
                return
            
            # Montar texto final
            texto_final = (
                "> 💰 **REGISTRO DE ATENDIMENTO**\n"
                "> ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"> **LÍDER ATENDIDO:** {self.usuario_atendido.mention} ({self.usuario_atendido.display_name})\n"
                f"> **ID do Líder:** {self.usuario_atendido.id}\n"
                f"> **RESPONSÁVEL:** {self.responsavel.mention} ({self.responsavel.display_name})\n"
                f"> **ID do Responsável:** {self.responsavel.id}\n"
            )
            
            if self.auxiliares:
                auxiliares_texto = []
                for uid in self.auxiliares:
                    member = interaction.guild.get_member(uid)
                    if member:
                        auxiliares_texto.append(f"{member.mention} ({member.display_name} - ID: {uid})")
                    else:
                        auxiliares_texto.append(f"<@{uid}> (ID: {uid})")
                texto_final += f"> **AUXILIARES:** {', '.join(auxiliares_texto)}\n"
            
            texto_final += (
                f"> **MOTIVO:** {self.motivo_atendimento}\n"
                f"> **STATUS:** ✅ RESOLVIDO\n"
                f"> **CANAL:** {self.canal_atendimento.mention} ({self.canal_atendimento.name})\n"
                "> ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )
            
            await self.mensagem_original.edit(content=texto_final, view=None)
            
            await interaction.response.send_message(
                "✅ Atendimento finalizado com sucesso!",
                ephemeral=True
            )
            
            if self.atendimento_id in atendimentos_ativos:
                del atendimentos_ativos[self.atendimento_id]
            
            self.stop()
            
        except Exception as e:
            print(f"❌ Erro ao finalizar: {e}")
            traceback.print_exc()
            await interaction.response.send_message(
                "❌ Erro ao finalizar atendimento.",
                ephemeral=True
            )
    
    @ui.button(label='🛠️ AUXILIEI NO ATENDIMENTO', style=ButtonStyle.blurple, row=1)
    async def auxiliar_atendimento(self, interaction: discord.Interaction, button: ui.Button):
        try:
            # Verificar se o usuário é o responsável
            if self.responsavel and interaction.user.id == self.responsavel.id:
                await interaction.response.send_message(
                    "❌ Você é o **RESPONSÁVEL** por este atendimento e não pode se registrar como auxiliar!",
                    ephemeral=True
                )
                return
            
            if interaction.user.id in self.auxiliares:
                self.auxiliares.remove(interaction.user.id)
                button.label = '🛠️ AUXILIEI NO ATENDIMENTO'
                button.style = ButtonStyle.blurple
                msg = "✅ Você foi removido como auxiliar!"
            else:
                self.auxiliares.append(interaction.user.id)
                button.label = '❌ REMOVER AUXÍLIO'
                button.style = ButtonStyle.gray
                msg = "✅ Você foi registrado como auxiliar!"
            
            auxiliares_mentions = [f"<@{uid}>" for uid in self.auxiliares]
            
            # Verificar se já foi preenchido
            if self.motivo_atendimento and self.responsavel:
                content = (
                    f"📝 **REGISTRO DE ATENDIMENTO - PREENCHIDO**\n"
                    f"**Líder Atendido:** {self.usuario_atendido.mention}\n"
                    f"**Canal de Atendimento:** {self.canal_atendimento.mention}\n"
                    f"**Responsável:** {self.responsavel.mention}\n"
                    f"**Auxiliares:** {', '.join(auxiliares_mentions) if auxiliares_mentions else 'Nenhum'}\n"
                    f"**Motivo:** {self.motivo_atendimento}\n\n"
                    f"⚠️ **Aguardando finalização do atendimento...**"
                )
            else:
                content = (
                    f"📝 **REGISTRO DE ATENDIMENTO - EM ANDAMENTO**\n"
                    f"**Líder Atendido:** {self.usuario_atendido.mention}\n"
                    f"**Canal de Atendimento:** {self.canal_atendimento.mention}\n"
                    f"**Auxiliares:** {', '.join(auxiliares_mentions) if auxiliares_mentions else 'Nenhum'}\n\n"
                    f"Clique em **PREENCHER ATENDIMENTO** para adicionar informações."
                )
            
            await self.mensagem_original.edit(content=content, view=self)
            await interaction.response.send_message(msg, ephemeral=True)
            
        except Exception as e:
            print(f"❌ Erro no auxiliar: {e}")
            await interaction.response.send_message(
                "❌ Erro ao processar solicitação.",
                ephemeral=True
            )
    
    @ui.button(label='❌ CANCELAR', style=ButtonStyle.red, row=1)
    async def cancelar_atendimento(self, interaction: discord.Interaction, button: ui.Button):
        try:
            if not any(role.permissions.manage_messages for role in interaction.user.roles):
                await interaction.response.send_message(
                    "❌ Apenas staff pode cancelar atendimentos!",
                    ephemeral=True
                )
                return
            
            await self.mensagem_original.edit(
                content=(
                    "> ❌ **ATENDIMENTO CANCELADO**\n"
                    "> ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"> **LÍDER:** {self.usuario_atendido.mention}\n"
                    f"> **CANCELADO POR:** {interaction.user.mention}\n"
                    f"> **CANAL:** {self.canal_atendimento.mention}\n"
                    "> ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                ),
                view=None
            )
            
            await interaction.response.send_message("✅ Atendimento cancelado!", ephemeral=True)
            
            if self.atendimento_id in atendimentos_ativos:
                del atendimentos_ativos[self.atendimento_id]
            
            self.stop()
            
        except Exception as e:
            print(f"❌ Erro ao cancelar: {e}")
            await interaction.response.send_message(
                "❌ Erro ao cancelar atendimento.",
                ephemeral=True
            )

# ============================
# CLASSES DO SISTEMA DE MONITORAMENTO
# ============================

class SelecionarFaccaoPaginadaView(discord.ui.View):
    def __init__(self, autor_original):
        super().__init__(timeout=120)
        self.autor_original = autor_original
        self.current_page = 0
        self.faccoes_por_pagina = 25
        
        # Obter todas as facções
        cursor.execute('SELECT nome FROM faccoes ORDER BY nome')
        self.todas_faccoes = [f[0] for f in cursor.fetchall()]
        self.total_paginas = (len(self.todas_faccoes) + self.faccoes_por_pagina - 1) // self.faccoes_por_pagina
        
        self.atualizar_select()
        self.update_buttons()
    
    def atualizar_select(self):
        # Limpar selects existentes
        for item in self.children[:]:
            if isinstance(item, discord.ui.Select):
                self.remove_item(item)
        
        # Calcular facções para a página atual
        inicio = self.current_page * self.faccoes_por_pagina
        fim = inicio + self.faccoes_por_pagina
        faccoes_pagina = self.todas_faccoes[inicio:fim]
        
        # Criar options para o select
        options = []
        for faccao in faccoes_pagina:
            options.append(discord.SelectOption(
                label=faccao[:100],
                value=faccao,
                description=f"Selecionar {faccao}" if len(faccao) < 50 else None
            ))
        
        # Adicionar select
        self.select = discord.ui.Select(
            placeholder=f"Selecione a facção (Página {self.current_page + 1}/{self.total_paginas})",
            options=options,
            custom_id=f"select_page_{self.current_page}"
        )
        self.select.callback = self.selecionar_faccao
        self.add_item(self.select)
        
        # Reorganizar botões
        self.reorganizar_botoes()
    
    def reorganizar_botoes(self):
        # Remover botões existentes (exceto select)
        for item in self.children[:]:
            if isinstance(item, discord.ui.Button):
                self.remove_item(item)
        
        # Adicionar botões na ordem correta
        self.add_item(self.previous_button)
        self.add_item(self.page_label)
        self.add_item(self.next_button)
        self.add_item(self.close_button)
    
    def update_buttons(self):
        self.previous_button.disabled = self.current_page == 0
        self.next_button.disabled = self.current_page == self.total_paginas - 1
        self.page_label.label = f'Página {self.current_page + 1}/{self.total_paginas}'
    
    @discord.ui.button(label='◀ Anterior', style=discord.ButtonStyle.primary, row=1)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.autor_original:
            await interaction.response.send_message("❌ Apenas quem solicitou pode navegar.", ephemeral=True)
            return
        
        self.current_page -= 1
        self.atualizar_select()
        self.update_buttons()
        await interaction.response.edit_message(view=self)
    
    @discord.ui.button(label='Página 1/1', style=discord.ButtonStyle.secondary, disabled=True, row=1)
    async def page_label(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
    
    @discord.ui.button(label='Próxima ▶', style=discord.ButtonStyle.primary, row=1)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.autor_original:
            await interaction.response.send_message("❌ Apenas quem solicitou pode navegar.", ephemeral=True)
            return
        
        self.current_page += 1
        self.atualizar_select()
        self.update_buttons()
        await interaction.response.edit_message(view=self)
    
    @discord.ui.button(label='❌ Fechar', style=discord.ButtonStyle.danger, row=1)
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.autor_original:
            await interaction.response.send_message("❌ Apenas quem solicitou pode fechar.", ephemeral=True)
            return
        
        await interaction.response.edit_message(content="❌ Seleção cancelada.", view=None)
        self.stop()
    
    async def selecionar_faccao(self, interaction: discord.Interaction):
        if interaction.user != self.autor_original:
            await interaction.response.send_message("❌ Apenas quem solicitou pode selecionar.", ephemeral=True)
            return
        
        faccao_selecionada = self.select.values[0]
        
        # Criar view de confirmação
        confirm_view = ConfirmarLimpezaView(faccao_selecionada)
        
        await interaction.response.send_message(
            f"📦 **Facção selecionada:** {faccao_selecionada}\n\n"
            "🗑️ **Deseja apagar o histórico de médias desta facção?**\n"
            "Isso removerá todos os registros anteriores e marcará como RECÉM ENTREGUE.",
            view=confirm_view,
            ephemeral=True
        )

class ConfirmarLimpezaView(discord.ui.View):
    def __init__(self, faccao_nome):
        super().__init__(timeout=120)
        self.faccao_nome = faccao_nome

    @discord.ui.button(label='✅ SIM, Apagar Histórico', style=discord.ButtonStyle.danger)
    async def confirmar_limpeza(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            # Verificar se é administrador
            if not interaction.user.guild_permissions.administrator:
                await interaction.response.send_message("❌ Apenas administradores podem usar esta função!", ephemeral=True)
                return

            nome_faccao_formatado = formatar_nome_faccao(self.faccao_nome)
            data_atual = datetime.now()
            
            # Verificar se a facção existe
            cursor.execute('SELECT id FROM faccoes WHERE nome = ?', (nome_faccao_formatado,))
            result = cursor.fetchone()
            
            if result:
                faccao_id = result[0]
                
                # LIMPAR TODOS OS REGISTROS ANTERIORES DA FACÇÃO
                cursor.execute('DELETE FROM registros_players WHERE faccao_id = ?', (faccao_id,))
                registros_removidos = cursor.rowcount
                
                # Atualizar data de entrega e status
                cursor.execute(
                    'UPDATE faccoes SET data_entrega = ?, recem_entregue = ? WHERE id = ?',
                    (data_atual, True, faccao_id)
                )
                
                conn.commit()
                
                await interaction.response.edit_message(
                    content=f"✅ **{nome_faccao_formatado}** marcada como RECÉM ENTREGUE!\n"
                           f"🗑️ **{registros_removidos} registros** anteriores foram apagados.\n"
                           f"📅 **Data de entrega:** {ajustar_fuso_horario(data_atual)}",
                    view=None
                )
                
                print(f'✅ {nome_faccao_formatado} marcada como recém entregue - {registros_removidos} registros limpos')
                
                # Atualizar painel automaticamente
                if ATUALIZACAO_AUTOMATICA:
                    await asyncio.sleep(2)
                    await atualizar_painel_players()
                    
            else:
                await interaction.response.edit_message(
                    content=f"❌ Facção **{nome_faccao_formatado}** não encontrada!",
                    view=None
                )
                
        except Exception as e:
            await interaction.response.edit_message(
                content=f"❌ Erro ao processar: {str(e)}",
                view=None
            )
            print(f'❌ Erro em ConfirmarLimpezaView: {e}')

    @discord.ui.button(label='❌ NÃO, Cancelar', style=discord.ButtonStyle.secondary)
    async def cancelar_limpeza(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            content="❌ Operação cancelada. Nenhum dado foi alterado.",
            view=None
        )

class EstatisticasPaginadasView(discord.ui.View):
    def __init__(self, embeds, autor_original):
        super().__init__(timeout=120)
        self.embeds = embeds
        self.current_page = 0
        self.autor_original = autor_original
        self.update_buttons()
    
    def update_buttons(self):
        self.previous_button.disabled = self.current_page == 0
        self.next_button.disabled = self.current_page == len(self.embeds) - 1
        self.page_label.label = f'Página {self.current_page + 1}/{len(self.embeds)}'
    
    @discord.ui.button(label='◀ Anterior', style=discord.ButtonStyle.primary)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.autor_original:
            await interaction.response.send_message("❌ Apenas quem solicitou pode navegar.", ephemeral=True)
            return
            
        self.current_page -= 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)
    
    @discord.ui.button(label='Página 1/1', style=discord.ButtonStyle.secondary, disabled=True)
    async def page_label(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
    
    @discord.ui.button(label='Próxima ▶', style=discord.ButtonStyle.primary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.autor_original:
            await interaction.response.send_message("❌ Apenas quem solicitou pode fechar.", ephemeral=True)
            return
            
        self.current_page += 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)
    
    @discord.ui.button(label='❌ Fechar', style=discord.ButtonStyle.danger)
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.autor_original:
            await interaction.response.send_message("❌ Apenas quem solicitou pode fechar.", ephemeral=True)
            return
            
        await interaction.response.edit_message(content="📊 **Estatísticas fechadas**", embed=None, view=None)
        self.stop()

class PainelPlayersView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label='🔄 Atualizar Painel', style=discord.ButtonStyle.primary, custom_id='atualizar_painel')
    async def atualizar_painel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await atualizar_painel_players()
        await interaction.followup.send('✅ Painel atualizado!', ephemeral=True)
    
    @discord.ui.button(label='📊 Estatísticas Completas', style=discord.ButtonStyle.secondary, custom_id='estatisticas_completas')
    async def estatisticas_completas(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        embeds = await criar_embeds_estatisticas_completas()
        
        if len(embeds) == 1:
            await interaction.followup.send(embed=embeds[0], ephemeral=True)
        else:
            view = EstatisticasPaginadasView(embeds, interaction.user)
            await interaction.followup.send(embed=embeds[0], view=view, ephemeral=True)
    
    @discord.ui.button(label='👥 Menos Players', style=discord.ButtonStyle.secondary, custom_id='menos_players')
    async def menos_players(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        embed = await criar_embed_menos_players()
        await interaction.followup.send(embed=embed, ephemeral=True)
    
    @discord.ui.button(label='📦 INFORMAR FAC ENTREGUE', style=discord.ButtonStyle.success, custom_id='informar_recem_entregue')
    async def informar_recem_entregue(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Verificar se é administrador
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Apenas administradores podem usar esta função!", ephemeral=True)
            return
        
        # Verificar se existem facções no banco
        cursor.execute('SELECT COUNT(*) FROM faccoes')
        total_faccoes = cursor.fetchone()[0]
        
        if total_faccoes == 0:
            await interaction.response.send_message("❌ Não há facções cadastradas no sistema!", ephemeral=True)
            return
        
        # Mostrar menu de seleção PAGINADO
        view = SelecionarFaccaoPaginadaView(interaction.user)
        
        mensagem_texto = (
            "📦 **SELECIONE A FACÇÃO RECÉM ENTREGUE**\n\n"
            f"**Total de facções:** {total_faccoes}\n"
            f"**Páginas disponíveis:** {view.total_paginas}\n\n"
            "Navegue pelas páginas e selecione a facção que foi entregue recentemente:"
        )
        
        await interaction.response.send_message(
            mensagem_texto,
            view=view,
            ephemeral=True
        )

# ============================
# FUNÇÕES DO SISTEMA DE MONITORAMENTO
# ============================

def ajustar_fuso_horario(data_utc):
    """Ajusta a data UTC para o fuso horário -3 (Brasília)"""
    if not data_utc:
        return "Nunca"
    
    try:
        if isinstance(data_utc, str):
            # Se for string, converter para datetime
            data_utc = datetime.fromisoformat(data_utc.replace('Z', '+00:00'))
        
        # Ajustar para fuso -3 (Brasília)
        fuso_brasilia = timedelta(hours=-3)
        data_brasilia = data_utc + fuso_brasilia
        
        # Formatar de forma elegante
        return data_brasilia.strftime('%d/%m/%Y %H:%M')
    
    except Exception as e:
        print(f"❌ Erro ao ajustar fuso horário: {e}")
        return "Data inválida"

def formatar_nome_faccao(nome: str) -> str:
    """Formata o nome da facção: primeira letra maiúscula e resto minúscula"""
    if not nome:
        return nome
    return nome[0].upper() + nome[1:].lower()

def verificar_faccao_recem_entregue(data_entrega):
    """Verifica se a facção foi entregue há menos de 7 dias"""
    if not data_entrega:
        return False
    
    try:
        if isinstance(data_entrega, str):
            data_entrega = datetime.fromisoformat(data_entrega.replace('Z', '+00:00'))
        
        dias_desde_entrega = (datetime.now() - data_entrega).days
        return dias_desde_entrega < 7
    except Exception:
        return False

async def processar_mensagem_entrega_faccoes(mensagem: discord.Message):
    """Processa mensagens no canal de entregas de facções para detectar facções recém-entregues"""
    content = mensagem.content.lower()
    
    # Padrões para detectar entrega de facções
    padroes_entrega = [
        r'entreg[ouáa].*fac[cç][aã]o.*?([a-zA-ZÀ-ÿ\s]+)',
        r'fac[cç][aã]o.*?([a-zA-ZÀ-ÿ\s]+).*entreg[ouáa]',
        r'([a-zA-ZÀ-ÿ\s]+).*foi.*entreg[ea]',
        r'nov[oa].*fac[cç][aã]o.*?([a-zA-ZÀ-ÿ\s]+)',
        r'fac[cç][aã]o.*?([a-zA-ZÀ-ÿ\s]+).*criad[oa]'
    ]
    
    faccoes_detectadas = []
    
    for padrao in padroes_entrega:
        matches = re.finditer(padrao, content)
        for match in matches:
            faccao_nome = match.group(1).strip()
            if len(faccao_nome) > 2:  # Nome válido deve ter mais de 2 caracteres
                faccoes_detectadas.append(faccao_nome)
    
    # Processar facções detectadas
    for faccao_nome in faccoes_detectadas:
        faccao_nome_formatado = formatar_nome_faccao(faccao_nome)
        
        # Verificar se a facção já existe
        cursor.execute('SELECT id, data_entrega FROM faccoes WHERE nome = ?', (faccao_nome_formatado,))
        result = cursor.fetchone()
        
        if result:
            faccao_id, data_entrega_existente = result
            # Atualizar data de entrega
            cursor.execute(
                'UPDATE faccoes SET data_entrega = ?, recem_entregue = ? WHERE id = ?',
                (mensagem.created_at, True, faccao_id)
            )
            print(f'🔄 Facção atualizada: {faccao_nome_formatado} - Data de entrega: {mensagem.created_at}')
        else:
            # Criar nova facção
            segmento = determinar_segmento(faccao_nome_formatado)
            cor = gerar_cor_aleatoria()
            
            cursor.execute(
                'INSERT INTO faccoes (nome, segmento, cor, data_entrega, recem_entregue) VALUES (?, ?, ?, ?, ?)',
                (faccao_nome_formatado, segmento, cor, mensagem.created_at, True)
            )
            print(f'➕ Nova facção entregue: {faccao_nome_formatado} - Data: {mensagem.created_at}')
    
    if faccoes_detectadas:
        conn.commit()
        return True
    
    return False

async def processar_mensagem_completa(mensagem: discord.Message):
    """Processa mensagens normais E embeds de outros bots"""
    print(f'📨 Mensagem recebida de {mensagem.author}')
    
    # Se for embed de outro bot, extrair conteúdo dos campos
    if mensagem.embeds:
        print("🔍 Mensagem contém EMBED - extraindo conteúdo...")
        content = await extrair_conteudo_embed(mensagem)
    else:
        content = mensagem.content
    
    print(f'📝 Conteúdo extraído: {content[:300]}...')
    
    # EXTRAIR DATA
    data_hora_original = mensagem.created_at
    data_pattern = r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})'
    data_match = re.search(data_pattern, content)
    
    if data_match:
        try:
            data_hora_str = data_match.group(1)
            data_hora_original = datetime.strptime(data_hora_str, '%Y-%m-%d %H:%M:%S')
            print(f'✅ Data/hora detectada: {data_hora_original}')
        except Exception as e:
            print(f'❌ Erro ao parsear data: {e}')

    # PADRÃO UNIVERSAL - captura QUALQUER texto: número
    padrao_universal = r'([a-zA-ZÀ-ÿ][a-zA-ZÀ-ÿ\s\-]*?)\s*:\s*(\d+)'
    
    registros_processados = 0
    faccoes_detectadas = []
    
    print("🔍 Procurando facções com padrão universal...")
    
    matches = re.findall(padrao_universal, content, re.IGNORECASE | re.MULTILINE)
    print(f"🎯 Padrão universal encontrou {len(matches)} matches")
    
    # LISTA DE NOMES A IGNORAR
    palavras_ignorar = [
        'nil', 'onil', 'municao', 'lavagem', 'drogas_desmanche', 'jogador', 
        'data', 'hora', 'orgs', 'itable', 'armas', 'table', 'tabela',
        'total', 'ilegais', 'online', 'media', 'semanal', 'ultimo', 'registro',
        'players', 'player', 'atualizar', 'painel', 'estatisticas', 'completas',
        'menos'
    ]
    
    for faccao_nome, quantidade_str in matches:
        faccao_nome = faccao_nome.strip()
        
        # IGNORAR NOMES ESPECÍFICOS E VALORES ACIMA DE 150
        try:
            quantidade = int(quantidade_str)
            
            # FILTRAR VALORES ACIMA DE 150
            if quantidade > 150:
                print(f"📊 Ignorando valor alto: '{faccao_nome}' -> {quantidade}")
                continue
                
        except ValueError:
            print(f"❌ Erro ao converter quantidade: '{quantidade_str}'")
            continue
        
        # IGNORAR PALAVRAS INDESEJADAS
        if (any(palavra in faccao_nome.lower() for palavra in palavras_ignorar) or 
            len(faccao_nome) < 2 or
            faccao_nome.lower() == 'tabela' or
            faccao_nome.lower() == 'table' or
            'total' in faccao_nome.lower() or
            'ilegais' in faccao_nome.lower()):
            print(f"🚫 Ignorando nome inválido: '{faccao_nome}'")
            continue
        
        try:
            quantidade = int(quantidade_str)
            print(f"🔍 Analisando: '{faccao_nome}' -> {quantidade}")
            
            # IGNORAR REGISTROS ZERADOS
            if quantidade == 0:
                continue
            
            # Formatar nome da facção
            faccao_nome_formatado = formatar_nome_faccao(faccao_nome)
            
            print(f"✅ Processando: {faccao_nome_formatado} -> {quantidade} players")
            
            # Verificar se a facção já existe no banco
            cursor.execute('SELECT id, nome, segmento, data_entrega FROM faccoes WHERE nome = ?', (faccao_nome_formatado,))
            result = cursor.fetchone()
            
            if not result:
                # Criar nova facção se não existir
                segmento = determinar_segmento(faccao_nome_formatado)
                cor = gerar_cor_aleatoria()
                
                cursor.execute(
                    'INSERT INTO faccoes (nome, segmento, cor) VALUES (?, ?, ?)',
                    (faccao_nome_formatado, segmento, cor)
                )
                faccao_id = cursor.lastrowid
                print(f'➕ Nova facção criada: {faccao_nome_formatado} ({segmento})')
            else:
                faccao_id, nome_existente, segmento, data_entrega = result
                print(f'🔄 Facção existente: {faccao_nome_formatado} (ID: {faccao_id})')
            
            # Inserir registro
            cursor.execute(
                'INSERT INTO registros_players (faccao_id, quantidade, data_hora_original) VALUES (?, ?, ?)',
                (faccao_id, quantidade, data_hora_original)
            )
            
            registros_processados += 1
            faccoes_detectadas.append(f"{faccao_nome_formatado}: {quantidade}")
            
        except ValueError:
            print(f"❌ Erro ao converter quantidade: '{quantidade_str}' para {faccao_nome}")
        except Exception as e:
            print(f"❌ Erro ao processar {faccao_nome}: {e}")
    
    if registros_processados > 0:
        conn.commit()
        print(f'✅ {registros_processados} registros processados - {", ".join(faccoes_detectadas)}')
        return True
    else:
        print(f'📭 Nenhum registro válido encontrado')
    
    return False

async def extrair_conteudo_embed(mensagem: discord.Message) -> str:
    """Extrai conteúdo de embeds de outros bots"""
    content = ""
    
    for embed in mensagem.embeds:
        # Título
        if embed.title:
            content += f"{embed.title}\n"
        
        # Descrição
        if embed.description:
            content += f"{embed.description}\n"
        
        # Campos
        for field in embed.fields:
            content += f"{field.name}: {field.value}\n"
        
        # Footer
        if embed.footer and embed.footer.text:
            content += f"{embed.footer.text}\n"
    
    # Se não conseguiu extrair do embed, usa o conteúdo normal
    if not content.strip():
        content = mensagem.content
    
    return content

def determinar_segmento(nome_faccao: str) -> str:
    """Determina o segmento baseado no nome da facção"""
    return "Não Classificado"

def gerar_cor_aleatoria():
    """Gera uma cor aleatória para a facção"""
    cores = [
        0xFF6B6B, 0x4ECDC4, 0x45B7D1, 0x96CEB4, 0xFECA57, 0xFF9FF3, 0x54A0FF,
        0x5F27CD, 0x00D2D3, 0xFF9F43, 0xA55EEA, 0xFD7272, 0x1B9CFC, 0xFC427B,
        0xBDC581, 0x82589F, 0x58B19F, 0xEAB543, 0x2C3A47, 0xB33771, 0x3B3B98,
        0xF97F51, 0x1B1464, 0xFFC048, 0xFF9F1A, 0x006266, 0xED4C67, 0x1289A7,
        0xD980FA, 0xFFC312, 0xC4E538, 0xFDA7DF, 0x9980FA, 0x833471, 0xFEA47F,
        0x25CCF7, 0xEAB543, 0x55E6C1, 0xCAD3C8, 0xF97F51
    ]
    return random.choice(cores)

async def calcular_medias_faccao(faccao_id: int) -> dict:
    """Calcula médias diárias, semanais e mensais para uma facção"""
    # Média das últimas 24 horas
    cursor.execute('''
        SELECT AVG(quantidade) 
        FROM registros_players 
        WHERE faccao_id = ? AND timestamp >= datetime('now', '-1 day')
    ''', (faccao_id,))
    media_diaria = cursor.fetchone()[0] or 0
    
    # Média dos últimos 7 dias
    cursor.execute('''
        SELECT AVG(quantidade) 
        FROM registros_players 
        WHERE faccao_id = ? AND timestamp >= datetime('now', '-7 days')
    ''', (faccao_id,))
    media_semanal = cursor.fetchone()[0] or 0
    
    # Média dos últimos 30 dias
    cursor.execute('''
        SELECT AVG(quantidade) 
        FROM registros_players 
        WHERE faccao_id = ? AND timestamp >= datetime('now', '-30 days')
    ''', (faccao_id,))
    media_mensal = cursor.fetchone()[0] or 0
    
    # Último registro
    cursor.execute('''
        SELECT quantidade, data_hora_original 
        FROM registros_players 
        WHERE faccao_id = ? 
        ORDER BY timestamp DESC 
        LIMIT 1
    ''', (faccao_id,))
    ultimo_registro = cursor.fetchone()
    
    # Verificar se é recém-entregue
    cursor.execute('SELECT data_entrega FROM faccoes WHERE id = ?', (faccao_id,))
    data_entrega = cursor.fetchone()[0]
    recem_entregue = verificar_faccao_recem_entregue(data_entrega)
    
    return {
        'diaria': round(media_diaria, 1),
        'semanal': round(media_semanal, 1),
        'mensal': round(media_mensal, 1),
        'ultimo': ultimo_registro[0] if ultimo_registro else 0,
        'ultima_atualizacao': ultimo_registro[1] if ultimo_registro else None,
        'recem_entregue': recem_entregue,
        'data_entrega': data_entrega
    }

def get_emoji_status(media_diaria: float) -> str:
    """Retorna emoji baseado na média diária"""
    if media_diaria < 10:
        return "🔴"  # Vermelho - menos de 10
    elif 10 <= media_diaria < 15:
        return "🟡"  # Amarelo - entre 10 e 15
    else:
        return "🟢"  # Verde - 15 ou mais

def get_emoji_posicao(posicao: int) -> str:
    """Retorna emoji de posição (1º, 2º, 3º)"""
    if posicao == 1:
        return "🥇"
    elif posicao == 2:
        return "🥈"
    elif posicao == 3:
        return "🥉"
    else:
        return f"{posicao}º"

async def criar_embed_painel() -> discord.Embed:
    """Cria o embed do painel principal com as TOP 5 facções"""
    embed = discord.Embed(
        title='🎮 **TOP 5 FACÇÕES - MAIORES MÉDIAS**',
        description='*Ranking das facções com maiores médias de players online*',
        color=0x00ff00
    )
    
    embed.set_thumbnail(url="https://i.ibb.co/tMyq1w9W/image.png")
    
    # Obter TOP 5 facções com maiores médias (últimas 24h)
    cursor.execute('''
        SELECT f.id, f.nome, f.segmento, f.cor, f.data_entrega,
               (SELECT AVG(quantidade) FROM registros_players rp 
                WHERE rp.faccao_id = f.id AND rp.timestamp >= datetime('now', '-1 day')) as media_diaria
        FROM faccoes f
        WHERE f.id IN (SELECT DISTINCT faccao_id FROM registros_players WHERE timestamp >= datetime('now', '-1 day'))
        ORDER BY media_diaria DESC
        LIMIT 5
    ''')
    
    top_faccoes = cursor.fetchall()
    
    if not top_faccoes:
        embed.add_field(
            name='📊 Dados',
            value='Nenhum registro encontrado nas últimas 24 horas.',
            inline=False
        )
        return embed
    
    # Última atualização geral
    cursor.execute('''
        SELECT MAX(data_hora_original) 
        FROM registros_players 
        WHERE timestamp >= datetime('now', '-1 day')
    ''')
    ultima_atualizacao_geral = cursor.fetchone()[0]
    
    # Adicionar cada facção com emoji de posição
    for idx, faccao in enumerate(top_faccoes, 1):
        faccao_id, nome, segmento, cor, data_entrega, media_diaria = faccao
        medias = await calcular_medias_faccao(faccao_id)
        
        emoji_status = get_emoji_status(medias['diaria'])
        emoji_posicao = get_emoji_posicao(idx)
        
        # Adicionar observação se for recém-entregue
        observacao = ""
        if medias['recem_entregue']:
            observacao = "\n🚨 **RECÉM ENTREGUE**"
        
        valor = (
            f"**📊 Média 24h:** `{medias['diaria']} players`\n"
            f"**📈 Média Semanal:** `{medias['semanal']} players`\n"
            f"**🎯 Último Registro:** `{medias['ultimo']} players`"
            f"{observacao}"
        )
        
        embed.add_field(
            name=f"{emoji_posicao} {emoji_status} {nome}",
            value=valor,
            inline=True
        )
    
    # Formatar última atualização com fuso -3
    if ultima_atualizacao_geral:
        atualizacao_texto = ajustar_fuso_horario(ultima_atualizacao_geral)
    else:
        atualizacao_texto = "Nunca"
    
    embed.set_footer(text=f'🕒 Última atualização: {atualizacao_texto} (Horário de Brasília)')
    
    return embed

async def criar_embed_menos_players() -> discord.Embed:
    """Cria embed com as facções com menor número de players online"""
    embed = discord.Embed(
        title='👥 **FACÇÕES COM MENOS PLAYERS ONLINE**',
        description='*Facções com menores médias nas últimas 24 horas*',
        color=0xFF6B6B
    )
    
    # Obter facções com menores médias (últimas 24h)
    cursor.execute('''
        SELECT f.id, f.nome, f.segmento, f.cor, f.data_entrega,
               (SELECT AVG(quantidade) FROM registros_players rp 
                WHERE rp.faccao_id = f.id AND rp.timestamp >= datetime('now', '-1 day')) as media_diaria
        FROM faccoes f
        WHERE f.id IN (SELECT DISTINCT faccao_id FROM registros_players WHERE timestamp >= datetime('now', '-1 day'))
        ORDER BY media_diaria ASC
        LIMIT 5
    ''')
    
    faccoes_menos_players = cursor.fetchall()
    
    if not faccoes_menos_players:
        embed.add_field(
            name='📊 Dados',
            value='Nenhum registro encontrado nas últimas 24 horas.',
            inline=False
        )
        return embed
    
    for faccao in faccoes_menos_players:
        faccao_id, nome, segmento, cor, data_entrega, media_diaria = faccao
        medias = await calcular_medias_faccao(faccao_id)
        
        emoji_status = get_emoji_status(medias['diaria'])
        
        # Adicionar observação se for recém-entregue
        observacao = ""
        if medias['recem_entregue']:
            observacao = " 🚨 **RECÉM ENTREGUE**"
        
        valor = (
            f"**Média 24h:** `{medias['diaria']} players`\n"
            f"**Último:** `{medias['ultimo']} players`{observacao}"
        )
        
        embed.add_field(
            name=f"{emoji_status} {nome}",
            value=valor,
            inline=True
        )
    
    return embed

async def criar_embeds_estatisticas_completas() -> list:
    """Cria múltiplos embeds com TODAS as facções divididas por segmento"""
    embeds = []
    
    # Obter todas as facções ordenadas por segmento e nome
    cursor.execute('''
        SELECT f.id, f.nome, f.segmento, f.cor, f.data_entrega
        FROM faccoes f
        ORDER BY f.segmento, f.nome
    ''')
    
    todas_faccoes = cursor.fetchall()
    
    if not todas_faccoes:
        embed = discord.Embed(
            title='📊 **ESTATÍSTICAS COMPLETAS**',
            description='Nenhuma facção cadastrada no sistema.',
            color=0x7289DA
        )
        return [embed]
    
    # Agrupar por segmento
    faccoes_por_segmento = {}
    for faccao in todas_faccoes:
        faccao_id, nome, segmento, cor, data_entrega = faccao
        if segmento not in faccoes_por_segmento:
            faccoes_por_segmento[segmento] = []
        faccoes_por_segmento[segmento].append(faccao)
    
    # Criar um embed por segmento
    for segmento, faccoes in faccoes_por_segmento.items():
        embed = discord.Embed(
            title=f'📊 **ESTATÍSTICAS - {segmento.upper()}**',
            color=0x7289DA
        )
        
        segmento_text = []
        
        for i, faccao in enumerate(faccoes):
            faccao_id, nome, segmento, cor, data_entrega = faccao
            medias = await calcular_medias_faccao(faccao_id)
            
            # Formatar última atualização com fuso -3
            ultima_atualizacao = "Nunca"
            if medias['ultima_atualizacao']:
                ultima_atualizacao = ajustar_fuso_horario(medias['ultima_atualizacao'])
            
            emoji_status = get_emoji_status(medias['diaria'])
            
            # Adicionar observação se for recém-entregue
            observacao = ""
            if medias['recem_entregue']:
                data_entrega_formatada = ajustar_fuso_horario(medias['data_entrega'])
                observacao = f"\n   🚨 **RECÉM ENTREGUE** ({data_entrega_formatada})"
            
            linha = (
                f"**─────────────────────────────────**\n"
                f"{emoji_status} **{nome}**\n"
                f"   📅 **Diária:** `{medias['diaria']}` | "
                f"📈 **Semanal:** `{medias['semanal']}` | "
                f"📊 **Mensal:** `{medias['mensal']}`\n"
                f"   ⏰ **Atualizado:** `{ultima_atualizacao}`"
                f"{observacao}"
            )
            
            if i == len(faccoes) - 1:
                linha += f"\n**─────────────────────────────────**"
            
            # Verificar se adicionar esta linha ultrapassaria o limite
            texto_atual = '\n'.join(segmento_text + [linha])
            if len(texto_atual) > 1024:
                embed.add_field(
                    name=f"🎯 {segmento} (Continuação)",
                    value='\n'.join(segmento_text),
                    inline=False
                )
                embeds.append(embed)
                
                # Criar novo embed para o restante
                embed = discord.Embed(
                    title=f'📊 **ESTATÍSTICAS - {segmento.upper()}**',
                    color=0x7289DA
                )
                segmento_text = [linha]
            else:
                segmento_text.append(linha)
        
        # Adicionar o que sobrou no segmento atual
        if segmento_text:
            embed.add_field(
                name=f"🎯 {segmento} ({len(faccoes)} facções)",
                value='\n'.join(segmento_text),
                inline=False
            )
            embeds.append(embed)
    
    # Adicionar estatísticas gerais no primeiro embed
    if embeds:
        cursor.execute('SELECT COUNT(*) FROM faccoes')
        total_faccoes = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(DISTINCT faccao_id) FROM registros_players WHERE timestamp >= datetime("now", "-1 day")')
        faccoes_ativas = cursor.fetchone()[0]
        
        cursor.execute('SELECT AVG(quantidade) FROM registros_players WHERE timestamp >= datetime("now", "-1 day")')
        media_geral = cursor.fetchone()[0] or 0
        
        cursor.execute('SELECT COUNT(*) FROM faccoes WHERE recem_entregue = 1')
        faccoes_recem_entregues = cursor.fetchone()[0]
        
        embeds[0].insert_field_at(
            0,
            name='📈 RESUMO GERAL',
            value=(
                f'**─────────────────────────────────**\n'
                f'**Total de Facções:** `{total_faccoes}`\n'
                f'**Facções Ativas (24h):** `{faccoes_ativas}`\n'
                f'**Taxa de Atividade:** `{(faccoes_ativas/total_faccoes*100):.1f}%`\n'
                f'**Média Geral:** `{media_geral:.1f} players`\n'
                f'**Recém Entregues:** `{faccoes_recem_entregues}`\n'
                f'**─────────────────────────────────**'
            ),
            inline=False
        )
    
    return embeds

async def atualizar_painel_players():
    """Atualiza o painel principal"""
    try:
        canal_painel = bot.get_channel(CANAL_PAINEL_ID)
        if not canal_painel:
            print('❌ Canal do painel não encontrado')
            return
        
        # Buscar a última mensagem do bot no canal
        async for mensagem in canal_painel.history(limit=10):
            if mensagem.author == bot.user and mensagem.components:
                # Atualizar mensagem existente
                embed = await criar_embed_painel()
                await mensagem.edit(embed=embed, view=PainelPlayersView())
                print('✅ Painel atualizado')
                return
        
        # Se não encontrou mensagem, criar nova
        embed = await criar_embed_painel()
        await canal_painel.send(embed=embed, view=PainelPlayersView())
        print('✅ Novo painel criado')
        
    except Exception as e:
        print(f'❌ Erro ao atualizar painel: {e}')

# ============================
# EVENTOS DO BOT
# ============================

@bot.event
async def on_voice_state_update(member, before, after):
    """Evento para sistema de atendimento - detecta quando membros entram em canais de atendimento"""
    try:
        if member.bot:
            return
        
        global ultimo_atendimento
        agora = time.time()
        
        if agora - ultimo_atendimento < RATE_LIMIT_SEGUNDOS:
            return
        
        if (before.channel and before.channel.id == CANAL_ORIGEM_ID and 
            after.channel and after.channel.id in CANAIS_ATENDIMENTO_IDS):
            
            ultimo_atendimento = agora
            atendimento_id = f"{member.id}_{int(agora)}"
            
            # Remover atendimentos anteriores do mesmo usuário
            for existing_id in list(atendimentos_ativos.keys()):
                if existing_id.startswith(str(member.id)):
                    del atendimentos_ativos[existing_id]
            
            atendimentos_ativos[atendimento_id] = {
                'member': member,
                'canal_atendimento': after.channel,
                'created_at': agora
            }
            
            await asyncio.sleep(3)
            
            try:
                member_check = after.channel.guild.get_member(member.id)
                if not member_check or not member_check.voice or member_check.voice.channel.id != after.channel.id:
                    if atendimento_id in atendimentos_ativos:
                        del atendimentos_ativos[atendimento_id]
                    return
            except:
                if atendimento_id in atendimentos_ativos:
                    del atendimentos_ativos[atendimento_id]
                return
            
            canal_registro = bot.get_channel(CANAL_REGISTRO_ID)
            if canal_registro:
                mensagem = await canal_registro.send(
                    f"📝 **REGISTRO DE ATENDIMENTO - EM ANDAMENTO**\n"
                    f"**Líder Atendido:** {member.mention}\n"
                    f"**Canal de Atendimento:** {after.channel.mention}\n"
                    f"**Auxiliares:** Nenhum\n\n"
                    f"Clique em **PREENCHER ATENDIMENTO** para adicionar informações."
                )
                
                view = AtendimentoView(member, after.channel, mensagem, atendimento_id)
                await mensagem.edit(view=view)
                print(f"✅ Atendimento iniciado: {member.display_name}")
                
    except Exception as e:
        print(f"❌ Erro em on_voice_state_update: {e}")
        traceback.print_exc()

@bot.event
async def on_message(mensagem):
    """Evento para sistema de monitoramento - processa mensagens nos canais específicos"""
    # Ignorar mensagens do próprio bot
    if mensagem.author == bot.user:
        return
    
    # Processar mensagens no canal de entrada de players
    if mensagem.channel.id == CANAL_ENTRADA_ID:
        print(f'📨 Mensagem recebida de {mensagem.author}')
        print(f'🔍 Tipo: {"EMBED" if mensagem.embeds else "TEXTO"}')
        print(f'📝 Conteúdo bruto: {mensagem.content[:100]}...')
        
        if mensagem.embeds:
            print(f'🎨 Embeds encontrados: {len(mensagem.embeds)}')
            for i, embed in enumerate(mensagem.embeds):
                print(f'   Embed {i+1}: {embed.title if embed.title else "Sem título"}')
        
        sucesso = await processar_mensagem_completa(mensagem)
        
        # Se processou com sucesso e atualização automática está ativa
        if sucesso and ATUALIZACAO_AUTOMATICA:
            await asyncio.sleep(2)
            await atualizar_painel_players()
    
    # Processar mensagens no canal de entregas de facções
    elif mensagem.channel.id == CANAL_FACCOES_ID:
        print(f'🏗️ Mensagem de entrega detectada: {mensagem.content[:100]}...')
        sucesso = await processar_mensagem_entrega_faccoes(mensagem)
        
        if sucesso:
            print('✅ Facção(ões) recém-entregue(s) processada(s)')

# ============================
# TASKS (LOOPS PERIÓDICOS)
# ============================

@tasks.loop(minutes=5)
async def limpar_atendimentos_orphaos():
    """Limpa atendimentos órfãos do sistema de atendimento"""
    try:
        agora = time.time()
        removidos = 0
        
        for atendimento_id in list(atendimentos_ativos.keys()):
            atendimento = atendimentos_ativos[atendimento_id]
            if agora - atendimento['created_at'] > 7200:
                del atendimentos_ativos[atendimento_id]
                removidos += 1
        
        if removidos > 0:
            print(f"🧹 Limpeza (Atendimento): {removidos} atendimentos órfãos removidos")
            
    except Exception as e:
        print(f"❌ Erro na limpeza de atendimentos: {e}")

@tasks.loop(minutes=5)
async def atualizacao_automatica():
    """Atualiza o painel automaticamente"""
    if ATUALIZACAO_AUTOMATICA:
        await atualizar_painel_players()
        print('🔄 Painel atualizado (atualização automática)')

@tasks.loop(hours=24)
async def atualizar_status_recem_entregue():
    """Atualiza o status 'recem_entregue' diariamente"""
    cursor.execute('''
        UPDATE faccoes 
        SET recem_entregue = 0 
        WHERE data_entrega IS NOT NULL 
        AND julianday('now') - julianday(data_entrega) >= 7
    ''')
    conn.commit()
    print('✅ Status "recem_entregue" atualizado')

# ============================
# EVENTO ON_READY
# ============================

@bot.event
async def on_ready():
    """Evento quando o bot está pronto"""
    bot.start_time = discord.utils.utcnow()
    print(f'✅ Bot {bot.user} online!')
    
    # Sistema de atendimento
    print(f'📞 Atendimento: Monitorando {len(CANAIS_ATENDIMENTO_IDS)} canais')
    limpar_atendimentos_orphaos.start()
    
    # Sistema de monitoramento
    print(f'📊 Monitoramento:')
    print(f'   📥 Canal de entrada: {CANAL_ENTRADA_ID}')
    print(f'   🏗️ Canal de facções: {CANAL_FACCOES_ID}')
    print(f'   📊 Canal do painel: {CANAL_PAINEL_ID}')
    
    # Iniciar atualização automática
    if ATUALIZACAO_AUTOMATICA:
        atualizacao_automatica.start()
        print('🔄 Atualização automática ativada (5 minutos)')
    
    # Iniciar atualização diária do status
    atualizar_status_recem_entregue.start()
    print('📅 Atualização diária de status ativada')

@bot.event
async def on_error(event, *args, **kwargs):
    print(f'❌ Erro no evento {event}:')
    traceback.print_exc()

# ============================
# EXECUÇÃO DO BOT
# ============================

print("🤖 Iniciando bot combinado (Atendimento + Monitoramento)...")
print("⚠️ IMPORTANTE: Substitua SEU_TOKEN_AQUI pelo seu token real!")


TOKEN = os.getenv('DISCORD_TOKEN')

if not TOKEN:
    print("❌ DISCORD_TOKEN não configurado!")
    print("💡 Configure em: Square Cloud → Your App → Variables")
    exit(1)


bot.run(TOKEN)
