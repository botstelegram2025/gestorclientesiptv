"""
Handlers do bot Telegram
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler, MessageHandler, filters

from config import *
from database import DatabaseManager
from notification_service_improved import NotificationServiceImproved
from utils import telefone_valido, get_duracao_meses, formatar_telefone, validar_data
from reports import ReportGenerator

logger = logging.getLogger(__name__)

class BotHandlers:
    """Classe para gerenciar todos os handlers do bot"""
    
    def __init__(self, db_manager: DatabaseManager, notification_service: NotificationServiceImproved):
        self.db = db_manager
        self.notification_service = notification_service
        self.report_generator = ReportGenerator(db_manager)
    
    def teclado_principal(self):
        """Retorna o teclado principal do bot"""
        teclado = [
            ["➕ Adicionar Cliente", "📋 Listar Clientes"],
            ["⏰ Filtrar Vencimentos", "📊 Relatório"],
            ["📤 Exportar Dados", "⚙️ Configurações"],
            ["📲 Envio Manual WhatsApp", "❌ Cancelar Operação"]
        ]
        return ReplyKeyboardMarkup(teclado, resize_keyboard=True)
    
    async def verificar_admin(self, update: Update) -> bool:
        """Verifica se o usuário é administrador"""
        if ADMIN_CHAT_ID == 0:
            return True  # Se não há admin configurado, permite acesso
        
        return update.effective_chat.id == ADMIN_CHAT_ID
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler para o comando /start"""
        if not await self.verificar_admin(update):
            await update.message.reply_text(MENSAGENS["acesso_negado"])
            return
        
        await update.message.reply_text(
            MENSAGENS["bem_vindo"],
            reply_markup=self.teclado_principal(),
            parse_mode='Markdown'
        )
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler para o comando /help"""
        await update.message.reply_text(
            MENSAGENS["ajuda"],
            parse_mode='Markdown'
        )
    
    async def menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler para mostrar o menu principal"""
        if not await self.verificar_admin(update):
            await update.message.reply_text(MENSAGENS["acesso_negado"])
            return
        
        await update.message.reply_text(
            "📋 *Menu Principal*\n\nEscolha uma opção:",
            reply_markup=self.teclado_principal(),
            parse_mode='Markdown'
        )
    
    async def cancelar(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Cancela a operação atual"""
        await update.message.reply_text(
            MENSAGENS["operacao_cancelada"],
            reply_markup=self.teclado_principal()
        )
        return ConversationHandler.END
    
    # Handlers para adicionar cliente
    async def adicionar_cliente_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Inicia o processo de adicionar cliente"""
        if not await self.verificar_admin(update):
            await update.message.reply_text(MENSAGENS["acesso_negado"])
            return ConversationHandler.END
        
        await update.message.reply_text(
            "➕ *Adicionar Novo Cliente*\n\n"
            "Digite o *nome completo* do cliente:",
            parse_mode='Markdown',
            reply_markup=ReplyKeyboardRemove()
        )
        return ADD_NAME
    
    async def adicionar_nome(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Recebe o nome do cliente"""
        nome = update.message.text.strip()
        
        if len(nome) < 3:
            await update.message.reply_text(
                "❌ Nome muito curto. Digite o nome completo do cliente:"
            )
            return ADD_NAME
        
        context.user_data['cliente_nome'] = nome
        
        await update.message.reply_text(
            f"✅ Nome: *{nome}*\n\n"
            "Digite o *telefone* do cliente (apenas números, 10 ou 11 dígitos):",
            parse_mode='Markdown'
        )
        return ADD_PHONE
    
    async def adicionar_telefone(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Recebe o telefone do cliente"""
        telefone = update.message.text.strip()
        
        if not telefone_valido(telefone):
            await update.message.reply_text(
                "❌ Telefone inválido. Digite apenas números (10 ou 11 dígitos):"
            )
            return ADD_PHONE
        
        # Verificar se o telefone já existe
        cliente_existente = self.db.buscar_cliente_por_telefone(telefone)
        if cliente_existente:
            await update.message.reply_text(
                f"❌ Este telefone já está cadastrado para: *{cliente_existente['nome']}*\n\n"
                "Digite outro telefone:",
                parse_mode='Markdown'
            )
            return ADD_PHONE
        
        context.user_data['cliente_telefone'] = telefone
        
        # Criar teclado com pacotes
        teclado = [[KeyboardButton(pacote)] for pacote in PACOTES]
        teclado.append([KeyboardButton("❌ Cancelar")])
        reply_markup = ReplyKeyboardMarkup(teclado, resize_keyboard=True)
        
        await update.message.reply_text(
            f"✅ Telefone: *{formatar_telefone(telefone)}*\n\n"
            "Selecione o *pacote*:",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        return ADD_PACOTE
    
    async def adicionar_pacote(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Recebe o pacote selecionado"""
        pacote = update.message.text.strip()
        
        if pacote == "❌ Cancelar":
            return await self.cancelar(update, context)
        
        if pacote not in PACOTES:
            await update.message.reply_text("❌ Pacote inválido. Selecione uma das opções:")
            return ADD_PACOTE
        
        context.user_data['cliente_pacote'] = pacote
        
        # Criar teclado com planos
        teclado = []
        for i in range(0, len(PLANOS), 2):
            linha = [KeyboardButton(f"R$ {PLANOS[i]:.2f}")]
            if i + 1 < len(PLANOS):
                linha.append(KeyboardButton(f"R$ {PLANOS[i+1]:.2f}"))
            teclado.append(linha)
        teclado.append([KeyboardButton("❌ Cancelar")])
        reply_markup = ReplyKeyboardMarkup(teclado, resize_keyboard=True)
        
        await update.message.reply_text(
            f"✅ Pacote: *{pacote}*\n\n"
            "Selecione o *valor do plano*:",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        return ADD_PLANO
    
    async def adicionar_plano(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Recebe o plano selecionado"""
        plano_text = update.message.text.strip()
        
        if plano_text == "❌ Cancelar":
            return await self.cancelar(update, context)
        
        try:
            # Extrair o valor numérico
            plano = float(plano_text.replace("R$", "").replace(",", ".").strip())
            if plano not in PLANOS:
                raise ValueError()
        except:
            await update.message.reply_text("❌ Plano inválido. Selecione uma das opções:")
            return ADD_PLANO
        
        context.user_data['cliente_plano'] = plano
        
        # Criar teclado com servidores
        teclado = []
        for servidor, emoji in SERVIDORES:
            teclado.append([KeyboardButton(f"{emoji} {servidor}")])
        teclado.append([KeyboardButton("❌ Cancelar")])
        reply_markup = ReplyKeyboardMarkup(teclado, resize_keyboard=True)
        
        await update.message.reply_text(
            f"✅ Plano: *R$ {plano:.2f}*\n\n"
            "Selecione o *servidor*:",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        return ADD_SERVIDOR
    
    async def adicionar_servidor(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Recebe o servidor selecionado e finaliza o cadastro"""
        servidor_text = update.message.text.strip()
        
        if servidor_text == "❌ Cancelar":
            return await self.cancelar(update, context)
        
        # Extrair nome do servidor (remover emoji)
        servidor = None
        for nome, emoji in SERVIDORES:
            if servidor_text == f"{emoji} {nome}":
                servidor = nome
                break
        
        if not servidor:
            await update.message.reply_text("❌ Servidor inválido. Selecione uma das opções:")
            return ADD_SERVIDOR
        
        # Calcular data de vencimento
        pacote = context.user_data['cliente_pacote']
        meses = get_duracao_meses(pacote)
        vencimento = (datetime.now() + timedelta(days=meses * 30)).strftime('%Y-%m-%d')
        
        # Salvar cliente no banco
        sucesso = self.db.adicionar_cliente(
            nome=context.user_data['cliente_nome'],
            telefone=context.user_data['cliente_telefone'],
            pacote=pacote,
            plano=context.user_data['cliente_plano'],
            vencimento=vencimento,
            servidor=servidor,
            chat_id=update.effective_chat.id
        )
        
        if sucesso:
            await update.message.reply_text(
                "✅ *Cliente cadastrado com sucesso!*\n\n"
                f"📝 *Nome:* {context.user_data['cliente_nome']}\n"
                f"📱 *Telefone:* {formatar_telefone(context.user_data['cliente_telefone'])}\n"
                f"📦 *Pacote:* {pacote}\n"
                f"💰 *Plano:* R$ {context.user_data['cliente_plano']:.2f}\n"
                f"🖥️ *Servidor:* {servidor}\n"
                f"📅 *Vencimento:* {datetime.strptime(vencimento, '%Y-%m-%d').strftime('%d/%m/%Y')}",
                parse_mode='Markdown',
                reply_markup=self.teclado_principal()
            )
        else:
            await update.message.reply_text(
                "❌ Erro ao cadastrar cliente. Tente novamente.",
                reply_markup=self.teclado_principal()
            )
        
        # Limpar dados temporários
        context.user_data.clear()
        return ConversationHandler.END
    
    # Handlers para listar clientes
    async def listar_clientes(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Lista todos os clientes cadastrados"""
        if not await self.verificar_admin(update):
            await update.message.reply_text(MENSAGENS["acesso_negado"])
            return
        
        clientes = self.db.listar_clientes()
        
        if not clientes:
            await update.message.reply_text(
                "📋 *Lista de Clientes*\n\n"
                "Nenhum cliente cadastrado ainda.",
                parse_mode='Markdown'
            )
            return
        
        # Dividir em páginas se houver muitos clientes
        clientes_por_pagina = 10
        total_paginas = (len(clientes) + clientes_por_pagina - 1) // clientes_por_pagina
        
        # Mostrar primeira página
        await self.mostrar_pagina_clientes(update, clientes, 1, total_paginas)
    
    async def mostrar_pagina_clientes(self, update: Update, clientes: list, pagina: int, total_paginas: int):
        """Mostra uma página específica da lista de clientes"""
        clientes_por_pagina = 10
        inicio = (pagina - 1) * clientes_por_pagina
        fim = inicio + clientes_por_pagina
        clientes_pagina = clientes[inicio:fim]
        
        texto = f"📋 *Lista de Clientes* (Página {pagina}/{total_paginas})\n\n"
        
        for i, cliente in enumerate(clientes_pagina, 1):
            vencimento = datetime.strptime(cliente['vencimento'], '%Y-%m-%d')
            dias_restantes = (vencimento - datetime.now()).days
            
            status = "🟢" if dias_restantes > 7 else "🟡" if dias_restantes > 0 else "🔴"
            
            texto += (
                f"{status} *{cliente['nome']}*\n"
                f"📱 {formatar_telefone(cliente['telefone'])}\n"
                f"💰 R$ {cliente['plano']:.2f} ({cliente['pacote']})\n"
                f"🖥️ {cliente['servidor']}\n"
                f"📅 Vence: {vencimento.strftime('%d/%m/%Y')} ({dias_restantes:+d} dias)\n\n"
            )
        
        # Criar botões de navegação se necessário
        keyboard = []
        if total_paginas > 1:
            nav_buttons = []
            if pagina > 1:
                nav_buttons.append(InlineKeyboardButton("⬅️ Anterior", callback_data=f"lista_pag_{pagina-1}"))
            if pagina < total_paginas:
                nav_buttons.append(InlineKeyboardButton("➡️ Próxima", callback_data=f"lista_pag_{pagina+1}"))
            if nav_buttons:
                keyboard.append(nav_buttons)
        
        # Botão para voltar ao menu
        keyboard.append([InlineKeyboardButton("🔙 Menu Principal", callback_data="menu_principal")])
        
        reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
        
        if update.callback_query:
            await update.callback_query.edit_message_text(
                texto,
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_text(
                texto,
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
    
    # Handlers para configurações
    async def configuracoes_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Mostra o menu de configurações"""
        if not await self.verificar_admin(update):
            await update.message.reply_text(MENSAGENS["acesso_negado"])
            return ConversationHandler.END
        
        config = self.db.get_configuracoes()
        
        texto = "⚙️ *Configurações do Sistema*\n\n"
        
        if config:
            texto += (
                f"🏢 *Empresa:* {config['empresa_nome'] or 'Não configurado'}\n"
                f"💳 *PIX:* {config['pix_key'] or 'Não configurado'}\n"
                f"📞 *Contato:* {config['contato_suporte'] or 'Não configurado'}\n\n"
            )
        else:
            texto += "Nenhuma configuração definida ainda.\n\n"
        
        teclado = [
            ["🏢 Configurar Empresa", "💳 Configurar PIX"],
            ["📞 Configurar Contato", "📄 Templates"],
            ["❌ Cancelar"]
        ]
        reply_markup = ReplyKeyboardMarkup(teclado, resize_keyboard=True)
        
        await update.message.reply_text(
            texto,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        return CONFIG_EMPRESA
    
    # Handlers para relatórios
    async def relatorio(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Gera relatório completo do sistema"""
        if not await self.verificar_admin(update):
            await update.message.reply_text(MENSAGENS["acesso_negado"])
            return
        
        relatorio = self.report_generator.gerar_relatorio_completo()
        
        await update.message.reply_text(
            relatorio,
            parse_mode='Markdown'
        )
    
    # Handlers para filtros de vencimento
    async def filtrar_vencimentos(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Mostra opções de filtro por vencimento"""
        if not await self.verificar_admin(update):
            await update.message.reply_text(MENSAGENS["acesso_negado"])
            return
        
        keyboard = [
            [InlineKeyboardButton("📅 Vencem Hoje", callback_data="filtro_hoje")],
            [InlineKeyboardButton("⚠️ Vencem Amanhã", callback_data="filtro_amanha")],
            [InlineKeyboardButton("📊 Vencem em 2 dias", callback_data="filtro_2dias")],
            [InlineKeyboardButton("📈 Vencem em 7 dias", callback_data="filtro_7dias")],
            [InlineKeyboardButton("🔴 Vencidos", callback_data="filtro_vencidos")],
            [InlineKeyboardButton("🔙 Menu Principal", callback_data="menu_principal")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "⏰ *Filtrar por Vencimento*\n\n"
            "Selecione o período que deseja visualizar:",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    
    # Handler para envio manual via WhatsApp
    async def envio_manual_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Inicia o processo de envio manual via WhatsApp"""
        if not await self.verificar_admin(update):
            await update.message.reply_text(MENSAGENS["acesso_negado"])
            return ConversationHandler.END
        
        await update.message.reply_text(
            "📲 *Envio Manual WhatsApp*\n\n"
            "Digite o *telefone* do destinatário (apenas números):",
            parse_mode='Markdown',
            reply_markup=ReplyKeyboardRemove()
        )
        return ENVIO_MANUAL_TELEFONE
    
    # Handler para exportar dados
    async def exportar_dados(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Exporta dados do sistema"""
        if not await self.verificar_admin(update):
            await update.message.reply_text(MENSAGENS["acesso_negado"])
            return
        
        try:
            # Gerar arquivo de exportação
            arquivo_csv = self.report_generator.exportar_clientes_csv()
            
            await update.message.reply_text(
                f"📤 *Dados Exportados*\n\n"
                f"Arquivo gerado: `{arquivo_csv}`\n"
                f"Data: {datetime.now().strftime('%d/%m/%Y %H:%M')}\n\n"
                "O arquivo contém todos os dados dos clientes em formato CSV.",
                parse_mode='Markdown'
            )
            
        except Exception as e:
            logger.error(f"Erro ao exportar dados: {e}")
            await update.message.reply_text(
                "❌ Erro ao exportar dados. Tente novamente."
            )
    
    # Handler para callback queries
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Manipula todas as callback queries"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        
        if data == "menu_principal":
            await query.edit_message_text(
                "📋 *Menu Principal*\n\nEscolha uma opção:",
                parse_mode='Markdown'
            )
            
        elif data.startswith("lista_pag_"):
            pagina = int(data.split("_")[2])
            clientes = self.db.listar_clientes()
            total_paginas = (len(clientes) + 9) // 10
            await self.mostrar_pagina_clientes(query, clientes, pagina, total_paginas)
            
        elif data.startswith("filtro_"):
            await self.processar_filtro_vencimento(query, data)
    
    async def processar_filtro_vencimento(self, query, filtro_tipo):
        """Processa filtros de vencimento"""
        if filtro_tipo == "filtro_hoje":
            clientes = self.db.clientes_vencendo(0)
            titulo = "📅 Clientes que vencem HOJE"
        elif filtro_tipo == "filtro_amanha":
            clientes = self.db.clientes_vencendo(1)
            titulo = "⚠️ Clientes que vencem AMANHÃ"
        elif filtro_tipo == "filtro_2dias":
            clientes = self.db.clientes_vencendo(2)
            titulo = "📊 Clientes que vencem em 2 DIAS"
        elif filtro_tipo == "filtro_7dias":
            clientes = self.db.clientes_vencendo(7)
            titulo = "📈 Clientes que vencem em 7 DIAS"
        elif filtro_tipo == "filtro_vencidos":
            clientes = self.db.clientes_vencidos()
            titulo = "🔴 Clientes VENCIDOS"
        else:
            return
        
        if not clientes:
            texto = f"{titulo}\n\nNenhum cliente encontrado neste período."
        else:
            texto = f"{titulo}\n\n"
            for cliente in clientes[:20]:  # Limitar a 20 para não exceder limite do Telegram
                vencimento = datetime.strptime(cliente['vencimento'], '%Y-%m-%d')
                texto += (
                    f"👤 *{cliente['nome']}*\n"
                    f"📱 {formatar_telefone(cliente['telefone'])}\n"
                    f"💰 R$ {cliente['plano']:.2f} ({cliente['pacote']})\n"
                    f"📅 {vencimento.strftime('%d/%m/%Y')}\n\n"
                )
            
            if len(clientes) > 20:
                texto += f"... e mais {len(clientes) - 20} clientes."
        
        keyboard = [[InlineKeyboardButton("🔙 Voltar", callback_data="menu_filtros")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            texto,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    
    # Handler para mensagens não reconhecidas
    async def mensagem_nao_reconhecida(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler para mensagens que não foram reconhecidas"""
        await update.message.reply_text(
            "❓ Comando não reconhecido.\n\n"
            "Use o menu abaixo ou digite /help para ver os comandos disponíveis.",
            reply_markup=self.teclado_principal()
        )
    
    def get_conversation_states(self):
        """Retorna os estados da conversa"""
        return {
            ADD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.adicionar_nome)],
            ADD_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.adicionar_telefone)],
            ADD_PACOTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.adicionar_pacote)],
            ADD_PLANO: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.adicionar_plano)],
            ADD_SERVIDOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.adicionar_servidor)],
            CONFIG_EMPRESA: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.configurar_empresa)],
            CONFIG_PIX: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.configurar_pix)],
            CONFIG_CONTATO: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.configurar_contato)],
            ENVIO_MANUAL_TELEFONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.envio_manual_telefone)],
            ENVIO_MANUAL_MENSAGEM: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.envio_manual_mensagem)]
        }
    
    # Handlers para configurações específicas
    async def configurar_empresa(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Configura o nome da empresa"""
        if update.message.text == "❌ Cancelar":
            return await self.cancelar(update, context)
        
        empresa = update.message.text.strip()
        context.user_data['config_empresa'] = empresa
        
        await update.message.reply_text(
            f"✅ Empresa: *{empresa}*\n\n"
            "Digite a *chave PIX* para pagamentos:",
            parse_mode='Markdown'
        )
        return CONFIG_PIX
    
    async def configurar_pix(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Configura a chave PIX"""
        if update.message.text == "❌ Cancelar":
            return await self.cancelar(update, context)
        
        pix = update.message.text.strip()
        context.user_data['config_pix'] = pix
        
        await update.message.reply_text(
            f"✅ PIX: *{pix}*\n\n"
            "Digite o *contato de suporte* (WhatsApp, Telegram, etc.):",
            parse_mode='Markdown'
        )
        return CONFIG_CONTATO
    
    async def configurar_contato(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Configura o contato de suporte e salva todas as configurações"""
        if update.message.text == "❌ Cancelar":
            return await self.cancelar(update, context)
        
        contato = update.message.text.strip()
        
        # Salvar todas as configurações
        sucesso = self.db.salvar_configuracoes(
            pix_key=context.user_data.get('config_pix', ''),
            empresa_nome=context.user_data.get('config_empresa', ''),
            contato_suporte=contato
        )
        
        if sucesso:
            await update.message.reply_text(
                "✅ *Configurações salvas com sucesso!*\n\n"
                f"🏢 *Empresa:* {context.user_data.get('config_empresa', '')}\n"
                f"💳 *PIX:* {context.user_data.get('config_pix', '')}\n"
                f"📞 *Contato:* {contato}",
                parse_mode='Markdown',
                reply_markup=self.teclado_principal()
            )
        else:
            await update.message.reply_text(
                "❌ Erro ao salvar configurações. Tente novamente.",
                reply_markup=self.teclado_principal()
            )
        
        context.user_data.clear()
        return ConversationHandler.END
    
    # Handlers para envio manual via WhatsApp
    async def envio_manual_telefone(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Recebe o telefone para envio manual"""
        if update.message.text == "❌ Cancelar":
            return await self.cancelar(update, context)
        
        telefone = update.message.text.strip()
        
        if not telefone_valido(telefone):
            await update.message.reply_text(
                "❌ Telefone inválido. Digite apenas números (10 ou 11 dígitos):"
            )
            return ENVIO_MANUAL_TELEFONE
        
        context.user_data['envio_telefone'] = telefone
        
        await update.message.reply_text(
            f"✅ Telefone: *{formatar_telefone(telefone)}*\n\n"
            "Digite a *mensagem* que deseja enviar:",
            parse_mode='Markdown'
        )
        return ENVIO_MANUAL_MENSAGEM
    
    async def envio_manual_mensagem(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Recebe a mensagem e envia via WhatsApp"""
        if update.message.text == "❌ Cancelar":
            return await self.cancelar(update, context)
        
        mensagem = update.message.text.strip()
        telefone = context.user_data['envio_telefone']
        
        # Enviar mensagem via WhatsApp
        sucesso = await self.notification_service.enviar_whatsapp_manual(telefone, mensagem)
        
        if sucesso:
            await update.message.reply_text(
                f"✅ *Mensagem enviada com sucesso!*\n\n"
                f"📱 *Para:* {formatar_telefone(telefone)}\n"
                f"💬 *Mensagem:* {mensagem[:100]}{'...' if len(mensagem) > 100 else ''}",
                parse_mode='Markdown',
                reply_markup=self.teclado_principal()
            )
        else:
            await update.message.reply_text(
                "❌ Erro ao enviar mensagem. Verifique a configuração da Evolution API.",
                reply_markup=self.teclado_principal()
            )
        
        context.user_data.clear()
        return ConversationHandler.END
    
    # Métodos adicionais necessários
    async def envio_manual_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Inicia o processo de envio manual via WhatsApp"""
        if not await self.verificar_admin(update):
            await update.message.reply_text(MENSAGENS["acesso_negado"])
            return ConversationHandler.END
        
        await update.message.reply_text(
            "📲 *Envio Manual via WhatsApp*\n\n"
            "Digite o *telefone* de destino (apenas números):",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove()
        )
        return ENVIO_MANUAL_TELEFONE
    
    async def exportar_dados(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Exporta dados do sistema"""
        if not await self.verificar_admin(update):
            await update.message.reply_text(MENSAGENS["acesso_negado"])
            return
        
        try:
            clientes_csv = self.report_generator.exportar_clientes_csv()
            renovacoes_csv = self.report_generator.exportar_renovacoes_csv()
            backup_json = self.report_generator.exportar_dados_json()
            
            await update.message.reply_text(
                f"✅ *Arquivos exportados com sucesso!*\n\n"
                f"📄 Clientes: `{clientes_csv}`\n"
                f"📋 Renovações: `{renovacoes_csv}`\n"
                f"💾 Backup: `{backup_json}`\n\n"
                f"📂 Pasta: reports/",
                parse_mode="Markdown"
            )
        except Exception as e:
            await update.message.reply_text(f"❌ Erro ao exportar: {str(e)}")
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler principal para botões inline"""
        query = update.callback_query
        await query.answer()
        
        if query.data == "menu_principal":
            await query.message.reply_text(
                "📋 *Menu Principal*",
                reply_markup=self.teclado_principal(),
                parse_mode="Markdown"
            )
        elif query.data.startswith("filtro_"):
            await self.processar_filtro_callback(query, query.data)
    
    async def processar_filtro_callback(self, query, data: str):
        """Processa callbacks dos filtros de vencimento"""
        dias_map = {
            "filtro_hoje": 0,
            "filtro_amanha": 1,
            "filtro_2_dias": 2,
            "filtro_7_dias": 7,
            "filtro_vencidos": -1
        }
        
        dias = dias_map.get(data, 0)
        
        if dias == -1:
            clientes = self.db.clientes_vencidos()
            titulo = "❌ CLIENTES VENCIDOS"
        else:
            clientes = self.db.clientes_vencendo(dias)
            titulo = f"📅 CLIENTES VENCENDO EM {dias} DIAS"
        
        if not clientes:
            texto = f"{titulo}\n\nNenhum cliente encontrado."
        else:
            texto = f"{titulo}\n\n"
            for i, cliente in enumerate(clientes[:10]):
                vencimento = datetime.strptime(cliente["vencimento"], "%Y-%m-%d")
                texto += (
                    f"{i+1}. *{cliente['nome']}*\n"
                    f"📱 {formatar_telefone(cliente['telefone'])}\n"
                    f"💰 R$ {cliente['plano']:.2f}\n"
                    f"📅 {vencimento.strftime('%d/%m/%Y')}\n\n"
                )
            
            if len(clientes) > 10:
                texto += f"... e mais {len(clientes) - 10} clientes."
        
        try:
            await query.edit_message_text(texto, parse_mode="Markdown")
        except Exception:
            await query.message.reply_text(texto, parse_mode="Markdown")

