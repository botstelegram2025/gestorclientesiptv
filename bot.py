#!/usr/bin/env python3
"""
Bot Telegram - Sistema de Gestão de Clientes - VERSÃO FINAL
Corrige problemas de loop de eventos e garante estabilidade
"""

import os
import sys
import logging
from datetime import datetime, timedelta
import pytz
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler, CallbackQueryHandler
from telegram import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton

# Configurar timezone brasileiro
TIMEZONE_BR = pytz.timezone('America/Sao_Paulo')

def agora_br():
    """Retorna datetime atual no fuso horário de Brasília"""
    return datetime.now(TIMEZONE_BR)

def converter_para_br(dt):
    """Converte datetime para timezone brasileiro"""
    if dt.tzinfo is None:
        # Se não tem timezone, assume UTC
        dt = pytz.utc.localize(dt)
    return dt.astimezone(TIMEZONE_BR)

def formatar_data_br(dt):
    """Formata data/hora no padrão brasileiro"""
    if isinstance(dt, str):
        dt = datetime.strptime(dt, '%Y-%m-%d')
    return dt.strftime('%d/%m/%Y')

def formatar_datetime_br(dt):
    """Formata data/hora completa no padrão brasileiro"""
    if dt.tzinfo is None:
        dt = TIMEZONE_BR.localize(dt)
    return dt.strftime('%d/%m/%Y às %H:%M')

def escapar_html(text):
    """Escapa caracteres especiais para HTML do Telegram"""
    if text is None:
        return ""
    text = str(text)
    # Escapar caracteres especiais do HTML
    text = text.replace('&', '&amp;')
    text = text.replace('<', '&lt;')
    text = text.replace('>', '&gt;')
    text = text.replace('"', '&quot;')
    text = text.replace("'", '&#x27;')
    return text

# Configurar logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO)
logger = logging.getLogger(__name__)

# Estados da conversação para cadastro de cliente
NOME, TELEFONE, PACOTE, VALOR, SERVIDOR, VENCIMENTO, CONFIRMAR = range(7)

# Estados para edição de cliente
EDIT_NOME, EDIT_TELEFONE, EDIT_PACOTE, EDIT_VALOR, EDIT_SERVIDOR, EDIT_VENCIMENTO = range(
    7, 13)

# Estados para configurações
CONFIG_EMPRESA, CONFIG_PIX, CONFIG_SUPORTE = range(13, 16)

def criar_teclado_principal():
    """Cria o teclado persistente com os botões principais organizados"""
    keyboard = [
        # Gestão de Clientes
        [
            KeyboardButton("👥 Listar Clientes"),
            KeyboardButton("➕ Adicionar Cliente")
        ],
        [KeyboardButton("🔍 Buscar Cliente"),
         KeyboardButton("📊 Relatórios")],

        # Sistema de Mensagens
        [KeyboardButton("📄 Templates"),
         KeyboardButton("⏰ Agendador")],
        [
            KeyboardButton("📋 Fila de Mensagens"),
            KeyboardButton("📜 Logs de Envios")
        ],

        # WhatsApp
        [
            KeyboardButton("📱 WhatsApp Status"),
            KeyboardButton("🧪 Testar WhatsApp")
        ],
        [KeyboardButton("📱 QR Code"),
         KeyboardButton("⚙️ Gerenciar WhatsApp")],

        # Configurações
        [
            KeyboardButton("🏢 Empresa"),
            KeyboardButton("💳 PIX"),
            KeyboardButton("📞 Suporte")
        ],
        [KeyboardButton("❓ Ajuda")]
    ]
    return ReplyKeyboardMarkup(keyboard,
                               resize_keyboard=True,
                               one_time_keyboard=False)

def criar_teclado_cancelar():
    """Cria teclado com opção de cancelar"""
    keyboard = [[KeyboardButton("❌ Cancelar")]]
    return ReplyKeyboardMarkup(keyboard,
                               resize_keyboard=True,
                               one_time_keyboard=True)

def criar_teclado_confirmar():
    """Cria teclado para confirmação"""
    keyboard = [[KeyboardButton("✅ Confirmar"),
                 KeyboardButton("✏️ Editar")], [KeyboardButton("❌ Cancelar")]]
    return ReplyKeyboardMarkup(keyboard,
                               resize_keyboard=True,
                               one_time_keyboard=True)

def criar_teclado_planos():
    """Cria teclado com planos predefinidos"""
    keyboard = [[KeyboardButton("📅 1 mês"),
                 KeyboardButton("📅 3 meses")],
                [KeyboardButton("📅 6 meses"),
                 KeyboardButton("📅 1 ano")],
                [
                    KeyboardButton("✏️ Personalizado"),
                    KeyboardButton("❌ Cancelar")
                ]]
    return ReplyKeyboardMarkup(keyboard,
                               resize_keyboard=True,
                               one_time_keyboard=True)

def criar_teclado_vencimento():
    """Cria teclado para vencimento automático ou personalizado"""
    keyboard = [[
        KeyboardButton("✅ Usar data automática"),
        KeyboardButton("📅 Data personalizada")
    ], [KeyboardButton("❌ Cancelar")]]
    return ReplyKeyboardMarkup(keyboard,
                               resize_keyboard=True,
                               one_time_keyboard=True)

def criar_teclado_valores():
    """Cria teclado com valores predefinidos"""
    keyboard = [[
        KeyboardButton("💰 R$ 30,00"),
        KeyboardButton("💰 R$ 35,00"),
        KeyboardButton("💰 R$ 40,00")
    ],
                [
                    KeyboardButton("💰 R$ 45,00"),
                    KeyboardButton("💰 R$ 50,00"),
                    KeyboardButton("💰 R$ 60,00")
                ],
                [
                    KeyboardButton("💰 R$ 70,00"),
                    KeyboardButton("💰 R$ 90,00"),
                    KeyboardButton("💰 R$ 135,00")
                ],
                [
                    KeyboardButton("✏️ Valor personalizado"),
                    KeyboardButton("❌ Cancelar")
                ]]
    return ReplyKeyboardMarkup(keyboard,
                               resize_keyboard=True,
                               one_time_keyboard=True)

def verificar_admin(func):
    """Decorator para verificar se é admin"""

    async def wrapper(update, context):
        admin_id = int(os.getenv('ADMIN_CHAT_ID', '0'))
        if update.effective_chat.id != admin_id:
            await update.message.reply_text(
                "❌ Acesso negado. Apenas o admin pode usar este bot.")
            return
        return await func(update, context)

    return wrapper

@verificar_admin
async def start(update, context):
    """Comando /start"""
    nome_admin = update.effective_user.first_name

    try:
        from database import DatabaseManager
        db = DatabaseManager()
        total_clientes = len(db.listar_clientes())
    except:
        total_clientes = 0

    mensagem = f"""🤖 *Bot de Gestão de Clientes*

Olá *{nome_admin}*! 

✅ Sistema inicializado com sucesso!
📊 Total de clientes: {total_clientes}

Use os botões abaixo para navegar:
👥 *Listar Clientes* - Ver todos os clientes
➕ *Adicionar Cliente* - Cadastrar novo cliente
📊 *Relatórios* - Estatísticas do sistema
🔍 *Buscar Cliente* - Encontrar cliente específico
⚙️ *Configurações* - Configurar empresa
❓ *Ajuda* - Ajuda completa

🚀 Sistema 100% operacional!"""

    await update.message.reply_text(mensagem,
                                    parse_mode='Markdown',
                                    reply_markup=criar_teclado_principal())

# === SISTEMA DE CADASTRO ESCALONÁVEL ===

@verificar_admin
async def iniciar_cadastro(update, context):
    """Inicia o processo de cadastro de cliente"""
    await update.message.reply_text(
        "📝 *Cadastro de Novo Cliente*\n\n"
        "Vamos cadastrar um cliente passo a passo.\n\n"
        "**Passo 1/6:** Digite o *nome completo* do cliente:",
        parse_mode='Markdown',
        reply_markup=criar_teclado_cancelar())
    return NOME

async def receber_nome(update, context):
    """Recebe o nome do cliente"""
    if update.message.text == "❌ Cancelar":
        return await cancelar_cadastro(update, context)

    nome = update.message.text.strip()
    if len(nome) < 2:
        await update.message.reply_text(
            "❌ Nome muito curto. Digite um nome válido:",
            reply_markup=criar_teclado_cancelar())
        return NOME

    context.user_data['nome'] = nome

    await update.message.reply_text(
        f"✅ Nome: *{nome}*\n\n"
        "**Passo 2/6:** Digite o *telefone* (apenas números):\n\n"
        "*Exemplo:* 11999999999",
        parse_mode='Markdown',
        reply_markup=criar_teclado_cancelar())
    return TELEFONE

async def receber_telefone(update, context):
    """Recebe o telefone do cliente"""
    if update.message.text == "❌ Cancelar":
        return await cancelar_cadastro(update, context)

    telefone = update.message.text.strip().replace(' ', '').replace(
        '-', '').replace('(', '').replace(')', '')

    if not telefone.isdigit() or len(telefone) < 10:
        await update.message.reply_text(
            "❌ Telefone inválido. Digite apenas números (ex: 11999999999):",
            reply_markup=criar_teclado_cancelar())
        return TELEFONE

    context.user_data['telefone'] = telefone

    await update.message.reply_text(
        f"✅ Telefone: *{telefone}*\n\n"
        "**Passo 3/6:** Escolha o *plano de duração*:\n\n"
        "Selecione uma das opções ou digite um plano personalizado:",
        parse_mode='Markdown',
        reply_markup=criar_teclado_planos())
    return PACOTE

async def receber_pacote(update, context):
    """Recebe o pacote do cliente"""
    if update.message.text == "❌ Cancelar":
        return await cancelar_cadastro(update, context)

    texto = update.message.text.strip()

    # Processar botões de planos predefinidos
    if texto == "📅 1 mês":
        pacote = "Plano 1 mês"
    elif texto == "📅 3 meses":
        pacote = "Plano 3 meses"
    elif texto == "📅 6 meses":
        pacote = "Plano 6 meses"
    elif texto == "📅 1 ano":
        pacote = "Plano 1 ano"
    elif texto == "✏️ Personalizado":
        await update.message.reply_text(
            "✏️ Digite o nome do seu plano personalizado:\n\n"
            "*Exemplos:* Netflix Premium, Disney+ 4K, Combo Streaming",
            parse_mode='Markdown',
            reply_markup=criar_teclado_cancelar())
        return PACOTE
    else:
        # Plano personalizado digitado diretamente
        pacote = texto
        if len(pacote) < 2:
            await update.message.reply_text(
                "❌ Nome do pacote muito curto. Digite um nome válido:",
                reply_markup=criar_teclado_planos())
            return PACOTE

    context.user_data['pacote'] = pacote

    # Calcular data de vencimento automática baseada no plano
    hoje = agora_br().replace(tzinfo=None)
    duracao_msg = ""

    if "1 mês" in pacote:
        vencimento_auto = hoje + timedelta(days=30)
        duracao_msg = " (vence em 30 dias)"
    elif "3 meses" in pacote:
        vencimento_auto = hoje + timedelta(days=90)
        duracao_msg = " (vence em 90 dias)"
    elif "6 meses" in pacote:
        vencimento_auto = hoje + timedelta(days=180)
        duracao_msg = " (vence em 180 dias)"
    elif "1 ano" in pacote:
        vencimento_auto = hoje + timedelta(days=365)
        duracao_msg = " (vence em 1 ano)"
    else:
        vencimento_auto = hoje + timedelta(days=30)  # Padrão: 30 dias
        duracao_msg = " (vencimento padrão: 30 dias)"

    # Salvar data calculada automaticamente
    context.user_data['vencimento_auto'] = vencimento_auto.strftime('%Y-%m-%d')

    await update.message.reply_text(
        f"✅ Pacote: *{pacote}*{duracao_msg}\n\n"
        "**Passo 4/6:** Escolha o *valor mensal*:\n\n"
        "Selecione um valor ou digite um personalizado:",
        parse_mode='Markdown',
        reply_markup=criar_teclado_valores())
    return VALOR

async def receber_valor(update, context):
    """Recebe o valor do plano"""
    if update.message.text == "❌ Cancelar":
        return await cancelar_cadastro(update, context)

    texto = update.message.text.strip()

    # Processar botões de valores predefinidos
    if texto == "💰 R$ 30,00":
        valor = 30.00
    elif texto == "💰 R$ 35,00":
        valor = 35.00
    elif texto == "💰 R$ 40,00":
        valor = 40.00
    elif texto == "💰 R$ 45,00":
        valor = 45.00
    elif texto == "💰 R$ 50,00":
        valor = 50.00
    elif texto == "💰 R$ 60,00":
        valor = 60.00
    elif texto == "💰 R$ 70,00":
        valor = 70.00
    elif texto == "💰 R$ 90,00":
        valor = 90.00
    elif texto == "💰 R$ 135,00":
        valor = 135.00
    elif texto == "✏️ Valor personalizado":
        await update.message.reply_text(
            "✏️ Digite o valor personalizado:\n\n"
            "*Exemplos:* 25.90, 85, 149.99",
            parse_mode='Markdown',
            reply_markup=criar_teclado_cancelar())
        return VALOR
    else:
        # Valor personalizado digitado diretamente
        try:
            valor_str = texto.replace(',', '.').replace('R$',
                                                        '').replace(' ', '')
            valor = float(valor_str)
            if valor <= 0:
                raise ValueError("Valor deve ser positivo")
        except ValueError:
            await update.message.reply_text(
                "❌ Valor inválido. Digite um número válido (ex: 25.90):",
                reply_markup=criar_teclado_valores())
            return VALOR

    context.user_data['valor'] = valor

    await update.message.reply_text(
        f"✅ Valor: *R$ {valor:.2f}*\n\n"
        "**Passo 5/6:** Digite o *servidor*:\n\n"
        "*Exemplos:* Servidor 1, Premium Server, Fast Play",
        parse_mode='Markdown',
        reply_markup=criar_teclado_cancelar())
    return SERVIDOR

async def receber_servidor(update, context):
    """Recebe o servidor"""
    if update.message.text == "❌ Cancelar":
        return await cancelar_cadastro(update, context)

    servidor = update.message.text.strip()
    if len(servidor) < 2:
        await update.message.reply_text(
            "❌ Nome do servidor muito curto. Digite um nome válido:",
            reply_markup=criar_teclado_cancelar())
        return SERVIDOR

    context.user_data['servidor'] = servidor

    # Mostrar opção de vencimento automático se disponível
    vencimento_auto = context.user_data.get('vencimento_auto')
    if vencimento_auto:
        data_formatada = datetime.strptime(vencimento_auto,
                                           '%Y-%m-%d').strftime('%d/%m/%Y')
        await update.message.reply_text(
            f"✅ Servidor: *{servidor}*\n\n"
            f"**Passo 6/6:** *Data de vencimento*\n\n"
            f"📅 *Data automática calculada:* {data_formatada}\n\n"
            "Deseja usar esta data ou personalizar?",
            parse_mode='Markdown',
            reply_markup=criar_teclado_vencimento())
    else:
        await update.message.reply_text(
            f"✅ Servidor: *{servidor}*\n\n"
            "**Passo 6/6:** Digite a *data de vencimento*:\n\n"
            "*Formato:* AAAA-MM-DD\n"
            "*Exemplo:* 2025-03-15",
            parse_mode='Markdown',
            reply_markup=criar_teclado_cancelar())
    return VENCIMENTO

async def receber_vencimento(update, context):
    """Recebe a data de vencimento"""
    if update.message.text == "❌ Cancelar":
        return await cancelar_cadastro(update, context)

    texto = update.message.text.strip()

    # Processar botões de vencimento
    if texto == "✅ Usar data automática":
        data_str = context.user_data.get('vencimento_auto')
        if not data_str:
            await update.message.reply_text(
                "❌ Erro: data automática não encontrada. Digite manualmente:",
                reply_markup=criar_teclado_cancelar())
            return VENCIMENTO
    elif texto == "📅 Data personalizada":
        await update.message.reply_text(
            "📅 Digite a data de vencimento personalizada:\n\n"
            "*Formato:* AAAA-MM-DD\n"
            "*Exemplo:* 2025-03-15",
            parse_mode='Markdown',
            reply_markup=criar_teclado_cancelar())
        return VENCIMENTO
    else:
        # Data digitada manualmente
        data_str = texto

        try:
            data_obj = datetime.strptime(data_str, '%Y-%m-%d')
            if data_obj < agora_br().replace(tzinfo=None):
                await update.message.reply_text(
                    "❌ Data não pode ser no passado. Digite uma data futura:",
                    reply_markup=criar_teclado_cancelar())
                return VENCIMENTO
        except ValueError:
            await update.message.reply_text(
                "❌ Data inválida. Use o formato AAAA-MM-DD (ex: 2025-03-15):",
                reply_markup=criar_teclado_vencimento())
            return VENCIMENTO

    context.user_data['vencimento'] = data_str
    data_obj = datetime.strptime(data_str, '%Y-%m-%d')

    # Mostrar resumo para confirmação
    dados = context.user_data
    data_formatada = data_obj.strftime('%d/%m/%Y')

    resumo = f"""📋 *CONFIRMAR CADASTRO*

📝 *Nome:* {dados['nome']}
📱 *Telefone:* {dados['telefone']}
📦 *Pacote:* {dados['pacote']}
💰 *Valor:* R$ {dados['valor']:.2f}
🖥️ *Servidor:* {dados['servidor']}
📅 *Vencimento:* {data_formatada}

Os dados estão corretos?"""

    await update.message.reply_text(resumo,
                                    parse_mode='Markdown',
                                    reply_markup=criar_teclado_confirmar())
    return CONFIRMAR

async def confirmar_cadastro(update, context):
    """Confirma e salva o cadastro"""
    if update.message.text == "❌ Cancelar":
        return await cancelar_cadastro(update, context)
    elif update.message.text == "✏️ Editar":
        await update.message.reply_text(
            "✏️ *Qual campo deseja editar?*\n\n"
            "Digite o número:\n"
            "1 - Nome\n"
            "2 - Telefone\n"
            "3 - Pacote\n"
            "4 - Valor\n"
            "5 - Servidor\n"
            "6 - Vencimento",
            parse_mode='Markdown',
            reply_markup=criar_teclado_cancelar())
        return CONFIRMAR
    elif update.message.text == "✅ Confirmar":
        # Salvar no banco
        try:
            from database import DatabaseManager
            db = DatabaseManager()
            dados = context.user_data

            sucesso = db.adicionar_cliente(dados['nome'], dados['telefone'],
                                           dados['pacote'], dados['valor'],
                                           dados['vencimento'],
                                           dados['servidor'])

            if sucesso:
                data_formatada = datetime.strptime(
                    dados['vencimento'], '%Y-%m-%d').strftime('%d/%m/%Y')
                await update.message.reply_text(
                    f"✅ *CLIENTE CADASTRADO COM SUCESSO!*\n\n"
                    f"📝 {dados['nome']}\n"
                    f"📱 {dados['telefone']}\n"
                    f"📦 {dados['pacote']}\n"
                    f"💰 R$ {dados['valor']:.2f}\n"
                    f"🖥️ {dados['servidor']}\n"
                    f"📅 {data_formatada}\n\n"
                    "Cliente adicionado ao sistema!",
                    parse_mode='Markdown',
                    reply_markup=criar_teclado_principal())
            else:
                await update.message.reply_text(
                    "❌ Erro ao salvar cliente. Tente novamente.",
                    reply_markup=criar_teclado_principal())

            # Limpar dados temporários
            context.user_data.clear()
            return ConversationHandler.END

        except Exception as e:
            logger.error(f"Erro ao cadastrar cliente: {e}")
            await update.message.reply_text(
                "❌ Erro interno. Tente novamente mais tarde.",
                reply_markup=criar_teclado_principal())
            context.user_data.clear()
            return ConversationHandler.END

    # Se chegou aqui, é um número para editar
    try:
        opcao = int(update.message.text)
        if opcao == 1:
            await update.message.reply_text(
                "Digite o novo nome:", reply_markup=criar_teclado_cancelar())
            return NOME
        elif opcao == 2:
            await update.message.reply_text(
                "Digite o novo telefone:",
                reply_markup=criar_teclado_cancelar())
            return TELEFONE
        elif opcao == 3:
            await update.message.reply_text(
                "Digite o novo pacote:", reply_markup=criar_teclado_cancelar())
            return PACOTE
        elif opcao == 4:
            await update.message.reply_text(
                "Digite o novo valor:", reply_markup=criar_teclado_cancelar())
            return VALOR
        elif opcao == 5:
            await update.message.reply_text(
                "Digite o novo servidor:",
                reply_markup=criar_teclado_cancelar())
            return SERVIDOR
        elif opcao == 6:
            await update.message.reply_text(
                "Digite a nova data (AAAA-MM-DD):",
                reply_markup=criar_teclado_cancelar())
            return VENCIMENTO
    except ValueError:
        pass

    await update.message.reply_text(
        "❌ Opção inválida. Use os botões ou digite um número de 1 a 6:",
        reply_markup=criar_teclado_confirmar())
    return CONFIRMAR

async def cancelar_cadastro(update, context):
    """Cancela o processo de cadastro"""
    context.user_data.clear()
    await update.message.reply_text("❌ Cadastro cancelado.",
                                    reply_markup=criar_teclado_principal())
    return ConversationHandler.END

# === FIM DO SISTEMA DE CADASTRO ===

@verificar_admin
async def add_cliente(update, context):
    """Adiciona cliente ao sistema"""
    try:
        texto = update.message.text.replace('/add ', '')
        partes = [p.strip() for p in texto.split('|')]

        if len(partes) != 6:
            await update.message.reply_text(
                "❌ Formato incorreto!\n\n"
                "Use: `/add Nome | Telefone | Pacote | Valor | Vencimento | Servidor`",
                parse_mode='Markdown')
            return

        nome, telefone, pacote, valor_str, vencimento, servidor = partes

        try:
            valor = float(valor_str)
        except ValueError:
            await update.message.reply_text(
                "❌ Valor deve ser um número válido!")
            return

        try:
            datetime.strptime(vencimento, '%Y-%m-%d')
        except ValueError:
            await update.message.reply_text(
                "❌ Data deve estar no formato AAAA-MM-DD!")
            return

        from database import DatabaseManager
        db = DatabaseManager()

        sucesso = db.adicionar_cliente(nome, telefone, pacote, valor,
                                       vencimento, servidor)

        if sucesso:
            await update.message.reply_text(
                f"✅ *Cliente adicionado com sucesso!*\n\n"
                f"📝 Nome: {nome}\n"
                f"📱 Telefone: {telefone}\n"
                f"📦 Pacote: {pacote}\n"
                f"💰 Valor: R$ {valor:.2f}\n"
                f"📅 Vencimento: {vencimento}\n"
                f"🖥️ Servidor: {servidor}",
                parse_mode='Markdown')
        else:
            await update.message.reply_text("❌ Erro ao adicionar cliente!")

    except Exception as e:
        logger.error(f"Erro ao adicionar cliente: {e}")
        await update.message.reply_text("❌ Erro interno do sistema!")

@verificar_admin
async def listar_clientes(update, context):
    """Lista todos os clientes com botões interativos ordenados por vencimento"""
    try:
        from database import DatabaseManager
        db = DatabaseManager()
        clientes = db.listar_clientes()

        if not clientes:
            await update.message.reply_text(
                "📋 Nenhum cliente cadastrado ainda.\n\n"
                "Use ➕ Adicionar Cliente para começar!",
                reply_markup=criar_teclado_principal())
            return

        # Ordenar clientes por data de vencimento (mais próximo primeiro)
        clientes_ordenados = []
        for cliente in clientes:
            try:
                vencimento = datetime.strptime(cliente['vencimento'],
                                               '%Y-%m-%d')
                cliente['vencimento_obj'] = vencimento
                cliente['dias_restantes'] = (
                    vencimento - agora_br().replace(tzinfo=None)).days
                clientes_ordenados.append(cliente)
            except (ValueError, KeyError) as e:
                logger.error(f"Erro ao processar cliente {cliente}: {e}")
                continue

        # Ordenar por data de vencimento (mais próximo primeiro)
        clientes_ordenados.sort(key=lambda x: x['vencimento_obj'])

        # Contar clientes por status para resumo
        total_clientes = len(clientes_ordenados)
        hoje = agora_br().replace(tzinfo=None)
        vencidos = len(
            [c for c in clientes_ordenados if c['dias_restantes'] < 0])
        vencendo_hoje = len(
            [c for c in clientes_ordenados if c['dias_restantes'] == 0])
        vencendo_breve = len(
            [c for c in clientes_ordenados if 0 < c['dias_restantes'] <= 3])
        ativos = total_clientes - vencidos

        mensagem = f"""👥 *LISTA DE CLIENTES*

📊 *Resumo:* {total_clientes} clientes
🔴 {vencidos} vencidos • ⚠️ {vencendo_hoje} hoje • 🟡 {vencendo_breve} em breve • 🟢 {ativos} ativos

💡 *Clique em um cliente para ver detalhes:*"""

        # Criar apenas botões inline para cada cliente
        keyboard = []

        for cliente in clientes_ordenados[:50]:  # Limitado a 50 botões
            dias_restantes = cliente['dias_restantes']
            vencimento = cliente['vencimento_obj']

            # Definir status e emoji
            if dias_restantes < 0:
                status_emoji = "🔴"
            elif dias_restantes == 0:
                status_emoji = "⚠️"
            elif dias_restantes <= 3:
                status_emoji = "🟡"
            else:
                status_emoji = "🟢"

            # Texto do botão com informações principais
            nome_curto = cliente['nome'][:18] + "..." if len(
                cliente['nome']) > 18 else cliente['nome']
            botao_texto = f"{status_emoji} {nome_curto} - R${cliente['plano']:.0f} - {vencimento.strftime('%d/%m')}"

            # Criar botão inline para cada cliente
            keyboard.append([
                InlineKeyboardButton(botao_texto,
                                     callback_data=f"cliente_{cliente['id']}")
            ])

        # Mostrar aviso se há mais clientes
        if total_clientes > 50:
            mensagem += f"\n\n⚠️ *Mostrando primeiros 50 de {total_clientes} clientes*\nUse 🔍 Buscar Cliente para encontrar outros."

        # Adicionar botões de ação geral
        keyboard.append([
            InlineKeyboardButton("🔄 Atualizar Lista",
                                 callback_data="atualizar_lista"),
            InlineKeyboardButton("📊 Relatório",
                                 callback_data="gerar_relatorio")
        ])

        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(mensagem,
                                        parse_mode='Markdown',
                                        reply_markup=reply_markup)

    except Exception as e:
        logger.error(f"Erro ao listar clientes: {e}")
        await update.message.reply_text("❌ Erro ao listar clientes!",
                                        reply_markup=criar_teclado_principal())

async def callback_cliente(update, context):
    """Lida com callbacks dos botões inline dos clientes"""
    query = update.callback_query
    await query.answer()

    data = query.data

    try:
        if data.startswith("cliente_"):
            # Mostrar detalhes do cliente específico
            cliente_id = int(data.split("_")[1])
            await mostrar_detalhes_cliente(query, context, cliente_id)

        elif data == "atualizar_lista":
            # Atualizar a lista de clientes
            await atualizar_lista_clientes(query, context)

        elif data == "gerar_relatorio":
            # Gerar relatório rápido
            await gerar_relatorio_inline(query, context)

        elif data == "voltar_lista":
            # Voltar para a lista de clientes
            await atualizar_lista_clientes(query, context)

        elif data.startswith("cobrar_"):
            # Enviar cobrança via WhatsApp
            cliente_id = int(data.split("_")[1])
            await enviar_cobranca_cliente(query, context, cliente_id)

        elif data.startswith("renovar_") and len(
                data.split("_")) == 3 and data.split("_")[1].isdigit():
            # Processar renovação por dias (formato: renovar_30_123)
            partes = data.split("_")
            dias = int(partes[1])
            cliente_id = int(partes[2])
            await processar_renovacao_cliente(query, context, cliente_id, dias)

        elif data.startswith("renovar_"):
            # Mostrar opções de renovação (formato: renovar_123)
            cliente_id = int(data.split("_")[1])
            await renovar_cliente_inline(query, context, cliente_id)

        elif data.startswith("editar_"):
            # Editar cliente
            cliente_id = int(data.split("_")[1])
            await editar_cliente_inline(query, context, cliente_id)

        elif data.startswith("excluir_"):
            # Excluir cliente
            cliente_id = int(data.split("_")[1])
            await excluir_cliente_inline(query, context, cliente_id)

        elif data.startswith("confirmar_excluir_"):
            # Confirmar exclusão
            cliente_id = int(data.split("_")[2])
            await confirmar_exclusao_cliente(query, context, cliente_id)

        elif data.startswith("edit_"):
            # Processar edição de campos específicos
            partes = data.split("_")
            if len(partes) == 3:
                campo = partes[1]
                cliente_id = int(partes[2])
                await iniciar_edicao_campo(query, context, cliente_id, campo)

    except Exception as e:
        logger.error(f"Erro no callback: {e}")
        await query.edit_message_text("❌ Erro ao processar ação!")

async def mostrar_detalhes_cliente(query, context, cliente_id):
    """Mostra detalhes completos de um cliente específico"""
    try:
        from database import DatabaseManager
        db = DatabaseManager()
        clientes = db.listar_clientes()

        cliente = next((c for c in clientes if c['id'] == cliente_id), None)
        if not cliente:
            await query.edit_message_text("❌ Cliente não encontrado!")
            return

        vencimento = datetime.strptime(cliente['vencimento'], '%Y-%m-%d')
        dias_restantes = (vencimento - agora_br().replace(tzinfo=None)).days

        # Status do cliente
        if dias_restantes < 0:
            status = f"🔴 VENCIDO há {abs(dias_restantes)} dias"
        elif dias_restantes == 0:
            status = "⚠️ VENCE HOJE"
        elif dias_restantes <= 3:
            status = f"🟡 VENCE EM {dias_restantes} DIAS"
        else:
            status = f"🟢 ATIVO ({dias_restantes} dias restantes)"

        mensagem = f"""👤 *DETALHES DO CLIENTE*

📝 *Nome:* {cliente['nome']}
📱 *Telefone:* {cliente['telefone']}
📦 *Pacote:* {cliente['pacote']}
💰 *Valor:* R$ {cliente['plano']:.2f}
🖥️ *Servidor:* {cliente['servidor']}
📅 *Vencimento:* {vencimento.strftime('%d/%m/%Y')}

📊 *Status:* {status}"""

        # Criar botões de ação para o cliente
        keyboard = [
            [
                InlineKeyboardButton("📧 Enviar Cobrança",
                                     callback_data=f"cobrar_{cliente_id}"),
                InlineKeyboardButton("🔄 Renovar",
                                     callback_data=f"renovar_{cliente_id}")
            ],
            [
                InlineKeyboardButton("✏️ Editar",
                                     callback_data=f"editar_{cliente_id}"),
                InlineKeyboardButton("🗑️ Excluir",
                                     callback_data=f"excluir_{cliente_id}")
            ],
            [
                InlineKeyboardButton("⬅️ Voltar à Lista",
                                     callback_data="voltar_lista")
            ]
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(mensagem,
                                      parse_mode='Markdown',
                                      reply_markup=reply_markup)

    except Exception as e:
        logger.error(f"Erro ao mostrar detalhes: {e}")
        await query.edit_message_text("❌ Erro ao carregar detalhes!")

async def atualizar_lista_clientes(query, context):
    """Atualiza a lista de clientes inline"""
    try:
        from database import DatabaseManager
        db = DatabaseManager()
        clientes = db.listar_clientes()

        if not clientes:
            await query.edit_message_text("📋 Nenhum cliente cadastrado ainda.")
            return

        # Recriar a lista ordenada (mesmo código da função listar_clientes)
        clientes_ordenados = []
        for cliente in clientes:
            try:
                vencimento = datetime.strptime(cliente['vencimento'],
                                               '%Y-%m-%d')
                cliente['vencimento_obj'] = vencimento
                cliente['dias_restantes'] = (
                    vencimento - agora_br().replace(tzinfo=None)).days
                clientes_ordenados.append(cliente)
            except (ValueError, KeyError):
                continue

        clientes_ordenados.sort(key=lambda x: x['vencimento_obj'])

        # Contar clientes por status para resumo
        total_clientes = len(clientes_ordenados)
        hoje = agora_br().replace(tzinfo=None)
        vencidos = len(
            [c for c in clientes_ordenados if c['dias_restantes'] < 0])
        vencendo_hoje = len(
            [c for c in clientes_ordenados if c['dias_restantes'] == 0])
        vencendo_breve = len(
            [c for c in clientes_ordenados if 0 < c['dias_restantes'] <= 3])
        ativos = total_clientes - vencidos

        mensagem = f"""👥 *LISTA DE CLIENTES*

📊 *Resumo:* {total_clientes} clientes
🔴 {vencidos} vencidos • ⚠️ {vencendo_hoje} hoje • 🟡 {vencendo_breve} em breve • 🟢 {ativos} ativos

💡 *Clique em um cliente para ver detalhes:*"""

        keyboard = []

        # Mostrar apenas botões, sem texto da lista
        for cliente in clientes_ordenados[:50]:  # Limitado a 50 botões
            dias_restantes = cliente['dias_restantes']
            vencimento = cliente['vencimento_obj']

            if dias_restantes < 0:
                status_emoji = "🔴"
            elif dias_restantes == 0:
                status_emoji = "⚠️"
            elif dias_restantes <= 3:
                status_emoji = "🟡"
            else:
                status_emoji = "🟢"

            nome_curto = cliente['nome'][:18] + "..." if len(
                cliente['nome']) > 18 else cliente['nome']
            botao_texto = f"{status_emoji} {nome_curto} - R${cliente['plano']:.0f} - {vencimento.strftime('%d/%m')}"

            keyboard.append([
                InlineKeyboardButton(botao_texto,
                                     callback_data=f"cliente_{cliente['id']}")
            ])

        keyboard.append([
            InlineKeyboardButton("🔄 Atualizar Lista",
                                 callback_data="atualizar_lista"),
            InlineKeyboardButton("📊 Relatório",
                                 callback_data="gerar_relatorio")
        ])

        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(mensagem,
                                      parse_mode='Markdown',
                                      reply_markup=reply_markup)

    except Exception as e:
        logger.error(f"Erro ao atualizar lista: {e}")
        await query.edit_message_text("❌ Erro ao atualizar lista!")

async def gerar_relatorio_inline(query, context):
    """Gera relatório rápido inline"""
    try:
        from database import DatabaseManager
        db = DatabaseManager()
        clientes = db.listar_clientes()

        total_clientes = len(clientes)
        receita_total = sum(float(c['plano']) for c in clientes)

        hoje = agora_br().replace(tzinfo=None)
        vencidos = [
            c for c in clientes
            if datetime.strptime(c['vencimento'], '%Y-%m-%d') < hoje
        ]
        vencendo_hoje = [
            c for c in clientes if c['vencimento'] == hoje.strftime('%Y-%m-%d')
        ]
        vencendo_3_dias = [
            c for c in clientes
            if 0 <= (datetime.strptime(c['vencimento'], '%Y-%m-%d') -
                     hoje).days <= 3
        ]

        # Usar horário brasileiro para o relatório
        agora_brasilia = agora_br()

        mensagem = f"""📊 *RELATÓRIO RÁPIDO*

👥 *Total de clientes:* {total_clientes}
💰 *Receita mensal:* R$ {receita_total:.2f}

📈 *Status dos Clientes:*
🔴 Vencidos: {len(vencidos)}
⚠️ Vencem hoje: {len(vencendo_hoje)}
🟡 Vencem em 3 dias: {len(vencendo_3_dias)}
🟢 Ativos: {total_clientes - len(vencidos)}

📅 *Atualizado:* {formatar_datetime_br(agora_brasilia)} (Brasília)"""

        keyboard = [[
            InlineKeyboardButton("⬅️ Voltar à Lista",
                                 callback_data="voltar_lista")
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(mensagem,
                                      parse_mode='Markdown',
                                      reply_markup=reply_markup)

    except Exception as e:
        logger.error(f"Erro no relatório: {e}")
        await query.edit_message_text("❌ Erro ao gerar relatório!")

async def enviar_cobranca_cliente(query, context, cliente_id):
    """Envia cobrança via WhatsApp para cliente específico"""
    try:
        from database import DatabaseManager
        from whatsapp_service import WhatsAppService
        from datetime import datetime

        db = DatabaseManager()
        clientes = db.listar_clientes(ativo_apenas=False)
        cliente = next((c for c in clientes if c['id'] == cliente_id), None)

        if not cliente:
            await query.edit_message_text("❌ Cliente não encontrado!")
            return

        # Preparar dados para envio
        vencimento = datetime.strptime(cliente['vencimento'], '%Y-%m-%d')
        dias_restantes = (vencimento - agora_br().replace(tzinfo=None)).days

        # Criar mensagem baseada no status
        if dias_restantes < 0:
            status_msg = f"VENCIDO há {abs(dias_restantes)} dias"
            urgencia = "🔴 URGENTE"
        elif dias_restantes == 0:
            status_msg = "VENCE HOJE"
            urgencia = "⚠️ ATENÇÃO"
        elif dias_restantes <= 3:
            status_msg = f"Vence em {dias_restantes} dias"
            urgencia = "🟡 LEMBRETE"
        else:
            status_msg = f"Vence em {dias_restantes} dias"
            urgencia = "🔔 LEMBRETE"

        # Montar mensagem de cobrança
        mensagem_whatsapp = f"""
{urgencia} - Renovação de Plano

Olá {cliente['nome']}!

📅 Status: {status_msg}
📦 Pacote: {cliente['pacote']}  
💰 Valor: R$ {cliente['plano']:.2f}
🖥️ Servidor: {cliente['servidor']}

Para renovar seu plano, entre em contato conosco.
"""

        # Enviar via WhatsApp com timeout
        try:
            ws = WhatsAppService()

            # Usar asyncio.wait_for para timeout de 10 segundos
            import asyncio
            sucesso = await asyncio.wait_for(ws.enviar_mensagem(
                cliente['telefone'], mensagem_whatsapp),
                                             timeout=10.0)

            if sucesso:
                mensagem = f"✅ *Cobrança Enviada!*\n\n📱 Cliente: {cliente['nome']}\n📞 WhatsApp: {cliente['telefone']}\n📅 Enviado: {agora_br().replace(tzinfo=None).strftime('%d/%m/%Y %H:%M')}"
            else:
                mensagem = f"❌ *Falha ao Enviar*\n\nO WhatsApp não confirmou o envio.\nVerifique se o número está correto."

        except asyncio.TimeoutError:
            mensagem = f"⏱️ *Timeout ao Enviar*\n\nA mensagem pode ter sido enviada mas demorou muito para responder.\nVerifique manualmente no WhatsApp."
        except Exception as e:
            logger.error(f"Erro específico ao enviar WhatsApp: {e}")
            mensagem = f"❌ *Erro ao Enviar*\n\nErro: {str(e)[:100]}\nVerifique as configurações da Evolution API."

        keyboard = [[
            InlineKeyboardButton("⬅️ Voltar ao Cliente",
                                 callback_data=f"cliente_{cliente_id}")
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(mensagem,
                                      parse_mode='Markdown',
                                      reply_markup=reply_markup)

    except Exception as e:
        logger.error(f"Erro ao enviar cobrança: {e}")
        keyboard = [[
            InlineKeyboardButton("⬅️ Voltar ao Cliente",
                                 callback_data=f"cliente_{cliente_id}")
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            f"❌ *Erro interno ao enviar cobrança!*\n\nDetalhes: {str(e)[:100]}",
            parse_mode='Markdown',
            reply_markup=reply_markup)

async def renovar_cliente_inline(query, context, cliente_id):
    """Renova cliente por período específico"""
    try:
        from database import DatabaseManager
        db = DatabaseManager()
        clientes = db.listar_clientes(
            ativo_apenas=False)  # Busca todos os clientes
        cliente = next((c for c in clientes if c['id'] == cliente_id), None)

        # Debug: vamos ver se o cliente existe
        logger.info(f"Procurando cliente ID: {cliente_id}")
        logger.info(f"Total de clientes encontrados: {len(clientes)}")
        if clientes:
            logger.info(f"IDs dos clientes: {[c['id'] for c in clientes]}")

        if not cliente:
            await query.edit_message_text(
                f"❌ Cliente ID {cliente_id} não encontrado!\nTotal clientes: {len(clientes)}"
            )
            return

        vencimento_atual = datetime.strptime(cliente['vencimento'], '%Y-%m-%d')

        mensagem = f"""🔄 *RENOVAR CLIENTE*

👤 *Cliente:* {cliente['nome']}
📅 *Vencimento Atual:* {vencimento_atual.strftime('%d/%m/%Y')}
📦 *Pacote:* {cliente['pacote']}
💰 *Valor:* R$ {cliente['plano']:.2f}

Escolha o período de renovação:"""

        keyboard = [
            [
                InlineKeyboardButton("📅 +30 dias",
                                     callback_data=f"renovar_30_{cliente_id}"),
                InlineKeyboardButton("📅 +60 dias",
                                     callback_data=f"renovar_60_{cliente_id}")
            ],
            [
                InlineKeyboardButton("📅 +90 dias",
                                     callback_data=f"renovar_90_{cliente_id}"),
                InlineKeyboardButton("📅 +365 dias",
                                     callback_data=f"renovar_365_{cliente_id}")
            ],
            [
                InlineKeyboardButton("⬅️ Voltar ao Cliente",
                                     callback_data=f"cliente_{cliente_id}")
            ]
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(mensagem,
                                      parse_mode='Markdown',
                                      reply_markup=reply_markup)

    except Exception as e:
        logger.error(f"Erro ao preparar renovação: {e}")
        await query.edit_message_text("❌ Erro ao preparar renovação!")

async def editar_cliente_inline(query, context, cliente_id):
    """Edita dados do cliente"""
    try:
        from database import DatabaseManager
        db = DatabaseManager()
        clientes = db.listar_clientes(ativo_apenas=False)
        cliente = next((c for c in clientes if c['id'] == cliente_id), None)

        if not cliente:
            await query.edit_message_text("❌ Cliente não encontrado!")
            return

        vencimento = datetime.strptime(cliente['vencimento'], '%Y-%m-%d')

        mensagem = f"""✏️ *EDITAR CLIENTE*

👤 *Cliente:* {cliente['nome']}
📱 *Telefone:* {cliente['telefone']}
📦 *Pacote:* {cliente['pacote']}
💰 *Valor:* R$ {cliente['plano']:.2f}
🖥️ *Servidor:* {cliente['servidor']}
📅 *Vencimento:* {vencimento.strftime('%d/%m/%Y')}

Escolha o que deseja editar:"""

        keyboard = [[
            InlineKeyboardButton("📝 Nome",
                                 callback_data=f"edit_nome_{cliente_id}"),
            InlineKeyboardButton("📱 Telefone",
                                 callback_data=f"edit_telefone_{cliente_id}")
        ],
                    [
                        InlineKeyboardButton(
                            "📦 Pacote",
                            callback_data=f"edit_pacote_{cliente_id}"),
                        InlineKeyboardButton(
                            "💰 Valor",
                            callback_data=f"edit_valor_{cliente_id}")
                    ],
                    [
                        InlineKeyboardButton(
                            "🖥️ Servidor",
                            callback_data=f"edit_servidor_{cliente_id}"),
                        InlineKeyboardButton(
                            "📅 Vencimento",
                            callback_data=f"edit_vencimento_{cliente_id}")
                    ],
                    [
                        InlineKeyboardButton(
                            "⬅️ Voltar ao Cliente",
                            callback_data=f"cliente_{cliente_id}")
                    ]]

        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(mensagem,
                                      parse_mode='Markdown',
                                      reply_markup=reply_markup)

    except Exception as e:
        logger.error(f"Erro ao preparar edição: {e}")
        await query.edit_message_text("❌ Erro ao preparar edição!")

async def excluir_cliente_inline(query, context, cliente_id):
    """Confirma exclusão do cliente"""
    try:
        from database import DatabaseManager
        db = DatabaseManager()
        clientes = db.listar_clientes(ativo_apenas=False)
        cliente = next((c for c in clientes if c['id'] == cliente_id), None)

        if not cliente:
            await query.edit_message_text("❌ Cliente não encontrado!")
            return

        vencimento = datetime.strptime(cliente['vencimento'], '%Y-%m-%d')

        mensagem = f"""🗑️ *EXCLUIR CLIENTE*

⚠️ *ATENÇÃO: Esta ação não pode ser desfeita!*

👤 *Cliente:* {cliente['nome']}
📱 *Telefone:* {cliente['telefone']}
📦 *Pacote:* {cliente['pacote']}
💰 *Valor:* R$ {cliente['plano']:.2f}
📅 *Vencimento:* {vencimento.strftime('%d/%m/%Y')}

Tem certeza que deseja excluir este cliente?"""

        keyboard = [[
            InlineKeyboardButton(
                "🗑️ SIM, EXCLUIR",
                callback_data=f"confirmar_excluir_{cliente_id}"),
            InlineKeyboardButton("❌ Cancelar",
                                 callback_data=f"cliente_{cliente_id}")
        ]]

        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(mensagem,
                                      parse_mode='Markdown',
                                      reply_markup=reply_markup)

    except Exception as e:
        logger.error(f"Erro ao preparar exclusão: {e}")
        await query.edit_message_text("❌ Erro ao preparar exclusão!")

async def confirmar_exclusao_cliente(query, context, cliente_id):
    """Executa a exclusão do cliente"""
    try:
        from database import DatabaseManager
        db = DatabaseManager()
        clientes = db.listar_clientes(ativo_apenas=False)
        cliente = next((c for c in clientes if c['id'] == cliente_id), None)

        if not cliente:
            await query.edit_message_text("❌ Cliente não encontrado!")
            return

        nome_cliente = cliente['nome']

        # Executar exclusão
        sucesso = db.excluir_cliente(cliente_id)

        if sucesso:
            mensagem = f"""✅ *CLIENTE EXCLUÍDO*

👤 Cliente: {nome_cliente}
🗑️ Removido do sistema em: {agora_br().replace(tzinfo=None).strftime('%d/%m/%Y %H:%M')}

O cliente foi permanentemente excluído do banco de dados."""
        else:
            mensagem = f"❌ *ERRO AO EXCLUIR*\n\nNão foi possível excluir o cliente {nome_cliente}.\nTente novamente mais tarde."

        keyboard = [[
            InlineKeyboardButton("⬅️ Voltar à Lista",
                                 callback_data="voltar_lista")
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(mensagem,
                                      parse_mode='Markdown',
                                      reply_markup=reply_markup)

    except Exception as e:
        logger.error(f"Erro ao excluir cliente: {e}")
        await query.edit_message_text("❌ Erro interno ao excluir cliente!")

async def processar_renovacao_cliente(query, context, cliente_id, dias):
    """Processa a renovação do cliente por X dias"""
    try:
        from database import DatabaseManager
        db = DatabaseManager()
        clientes = db.listar_clientes(ativo_apenas=False)
        cliente = next((c for c in clientes if c['id'] == cliente_id), None)

        if not cliente:
            await query.edit_message_text("❌ Cliente não encontrado!")
            return

        # Calcular nova data de vencimento
        from datetime import datetime, timedelta  # Import local para evitar conflitos
        vencimento_atual = datetime.strptime(cliente['vencimento'], '%Y-%m-%d')

        # Se já venceu, renovar a partir de hoje
        if vencimento_atual < agora_br().replace(tzinfo=None):
            nova_data = agora_br().replace(tzinfo=None) + timedelta(days=dias)
        else:
            # Se ainda não venceu, somar os dias ao vencimento atual
            nova_data = vencimento_atual + timedelta(days=dias)

        # Atualizar apenas a data de vencimento
        sucesso = db.atualizar_cliente(cliente_id, 'vencimento',
                                       nova_data.strftime('%Y-%m-%d'))

        if sucesso:
            # Registrar renovação no histórico
            db.registrar_renovacao(cliente_id, dias, cliente['plano'])

            mensagem = f"""✅ *CLIENTE RENOVADO*

👤 *Cliente:* {cliente['nome']}
⏰ *Período adicionado:* {dias} dias
📅 *Vencimento anterior:* {vencimento_atual.strftime('%d/%m/%Y')}
🔄 *Novo vencimento:* {nova_data.strftime('%d/%m/%Y')}
💰 *Valor:* R$ {cliente['plano']:.2f}

Renovação registrada com sucesso!"""
        else:
            mensagem = f"❌ *ERRO NA RENOVAÇÃO*\n\nNão foi possível renovar o cliente.\nTente novamente mais tarde."

        keyboard = [[
            InlineKeyboardButton("⬅️ Voltar ao Cliente",
                                 callback_data=f"cliente_{cliente_id}"),
            InlineKeyboardButton("📋 Ver Lista", callback_data="voltar_lista")
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(mensagem,
                                      parse_mode='Markdown',
                                      reply_markup=reply_markup)

    except Exception as e:
        logger.error(f"Erro ao renovar cliente: {e}")
        await query.edit_message_text("❌ Erro interno ao renovar cliente!")

async def iniciar_edicao_campo(query, context, cliente_id, campo):
    """Inicia a edição interativa de um campo específico do cliente"""
    try:
        from database import DatabaseManager
        db = DatabaseManager()
        clientes = db.listar_clientes(ativo_apenas=False)
        cliente = next((c for c in clientes if c['id'] == cliente_id), None)

        if not cliente:
            await query.edit_message_text("❌ Cliente não encontrado!")
            return

        # Salvar dados no contexto para a conversa de edição
        context.user_data['editando_cliente_id'] = cliente_id
        context.user_data['editando_campo'] = campo
        context.user_data['cliente_dados'] = cliente

        # Mapear campos e valores atuais
        campos_info = {
            'nome': {
                'label': 'Nome',
                'valor': cliente['nome'],
                'placeholder': 'Ex: João Silva Santos'
            },
            'telefone': {
                'label': 'Telefone',
                'valor': cliente['telefone'],
                'placeholder': 'Ex: 11999887766'
            },
            'pacote': {
                'label': 'Pacote',
                'valor': cliente['pacote'],
                'placeholder': 'Ex: Netflix Premium'
            },
            'valor': {
                'label': 'Valor',
                'valor': f"R$ {cliente['plano']:.2f}",
                'placeholder': 'Ex: 45.00'
            },
            'servidor': {
                'label': 'Servidor',
                'valor': cliente['servidor'],
                'placeholder': 'Ex: BR-SP01'
            },
            'vencimento': {
                'label':
                'Vencimento',
                'valor':
                datetime.strptime(cliente['vencimento'],
                                  '%Y-%m-%d').strftime('%d/%m/%Y'),
                'placeholder':
                'Ex: 15/03/2025'
            }
        }

        if campo not in campos_info:
            await query.edit_message_text("❌ Campo inválido!")
            return

        info = campos_info[campo]

        mensagem = f"""✏️ *EDITAR {info['label'].upper()}*

👤 *Cliente:* {cliente['nome']}
📝 *Campo:* {info['label']}
🔄 *Valor atual:* {info['valor']}

💬 Digite o novo {info['label'].lower()}:
{info['placeholder']}"""

        # Criar teclado com cancelar
        keyboard = [[KeyboardButton("❌ Cancelar")]]
        reply_markup = ReplyKeyboardMarkup(keyboard,
                                           resize_keyboard=True,
                                           one_time_keyboard=True)

        # Remover mensagem inline e enviar nova mensagem de texto
        await query.delete_message()
        await context.bot.send_message(chat_id=query.message.chat_id,
                                       text=mensagem,
                                       parse_mode='Markdown',
                                       reply_markup=reply_markup)

        # Mapear campo para estado
        estados_edicao = {
            'nome': EDIT_NOME,
            'telefone': EDIT_TELEFONE,
            'pacote': EDIT_PACOTE,
            'valor': EDIT_VALOR,
            'servidor': EDIT_SERVIDOR,
            'vencimento': EDIT_VENCIMENTO
        }

        return estados_edicao[campo]

    except Exception as e:
        logger.error(f"Erro ao iniciar edição: {e}")
        await query.edit_message_text("❌ Erro ao preparar edição!")

@verificar_admin
async def editar_cliente_cmd(update, context):
    """Comando para editar cliente via comando"""
    try:
        if len(context.args) < 3:
            await update.message.reply_text(
                "❌ Uso correto:\n"
                "`/editar ID campo valor`\n\n"
                "*Exemplo:*\n"
                "`/editar 1 nome João Silva`\n"
                "`/editar 1 valor 35.00`",
                parse_mode='Markdown',
                reply_markup=criar_teclado_principal())
            return

        cliente_id = int(context.args[0])
        campo = context.args[1].lower()
        novo_valor = " ".join(context.args[2:])

        from database import DatabaseManager
        db = DatabaseManager()
        clientes = db.listar_clientes()
        cliente = next((c for c in clientes if c['id'] == cliente_id), None)

        if not cliente:
            await update.message.reply_text(
                f"❌ Cliente com ID {cliente_id} não encontrado!",
                reply_markup=criar_teclado_principal())
            return

        # Validar campo e atualizar
        campos_validos = [
            'nome', 'telefone', 'pacote', 'valor', 'servidor', 'vencimento'
        ]
        if campo not in campos_validos:
            await update.message.reply_text(
                f"❌ Campo inválido! Use: {', '.join(campos_validos)}",
                reply_markup=criar_teclado_principal())
            return

        # Preparar dados para atualização
        dados = {
            'nome': cliente['nome'],
            'telefone': cliente['telefone'],
            'pacote': cliente['pacote'],
            'valor': cliente['plano'],
            'servidor': cliente['servidor'],
            'vencimento': cliente['vencimento']
        }

        # Aplicar mudança
        if campo == 'valor':
            try:
                dados['valor'] = float(novo_valor)
            except ValueError:
                await update.message.reply_text("❌ Valor deve ser um número!")
                return
        elif campo == 'vencimento':
            try:
                # Converter dd/mm/yyyy para yyyy-mm-dd
                if '/' in novo_valor:
                    dia, mes, ano = novo_valor.split('/')
                    novo_valor = f"{ano}-{mes.zfill(2)}-{dia.zfill(2)}"
                dados['vencimento'] = novo_valor
            except:
                await update.message.reply_text(
                    "❌ Data inválida! Use dd/mm/aaaa")
                return
        else:
            dados[campo] = novo_valor

        # Executar atualização
        sucesso = db.atualizar_cliente(cliente_id, campo, dados[campo])

        if sucesso:
            mensagem = f"""✅ *Cliente Atualizado!*
            
👤 *Nome:* {dados['nome']}
📱 *Telefone:* {dados['telefone']}
📦 *Pacote:* {dados['pacote']}
💰 *Valor:* R$ {dados['valor']:.2f}
🖥️ *Servidor:* {dados['servidor']}
📅 *Vencimento:* {datetime.strptime(dados['vencimento'], '%Y-%m-%d').strftime('%d/%m/%Y')}

🔄 *Campo alterado:* {campo.upper()}"""
        else:
            mensagem = "❌ Erro ao atualizar cliente!"

        await update.message.reply_text(mensagem,
                                        parse_mode='Markdown',
                                        reply_markup=criar_teclado_principal())

    except Exception as e:
        logger.error(f"Erro ao editar cliente: {e}")
        await update.message.reply_text("❌ Erro interno ao editar cliente!",
                                        reply_markup=criar_teclado_principal())

@verificar_admin
async def relatorio(update, context):
    """Gera relatório básico"""
    try:
        from database import DatabaseManager
        db = DatabaseManager()

        clientes = db.listar_clientes()
        total_clientes = len(clientes)
        receita_total = sum(float(c['plano']) for c in clientes)

        hoje = agora_br().replace(tzinfo=None).strftime('%Y-%m-%d')
        vencendo_hoje = [c for c in clientes if c['vencimento'] == hoje]

        mensagem = f"""📊 *RELATÓRIO GERAL*

👥 Total de clientes: {total_clientes}
💰 Receita mensal: R$ {receita_total:.2f}
⚠️ Vencendo hoje: {len(vencendo_hoje)}

📅 Data: {agora_br().replace(tzinfo=None).strftime('%d/%m/%Y %H:%M')}"""

        await update.message.reply_text(mensagem,
                                        parse_mode='Markdown',
                                        reply_markup=criar_teclado_principal())

    except Exception as e:
        logger.error(f"Erro no relatório: {e}")
        await update.message.reply_text("❌ Erro ao gerar relatório!")

@verificar_admin
async def help_cmd(update, context):
    """Comando de ajuda"""
    mensagem = """🆘 *COMANDOS DISPONÍVEIS*

*Gestão de Clientes:*
/start - Iniciar o bot
/addcliente - Como adicionar cliente
/add - Adicionar cliente
/listar - Listar todos os clientes
/relatorio - Relatório geral
/help - Esta ajuda

*Exemplo:*
`/add João Silva | 11999999999 | Netflix | 25.90 | 2025-03-15 | Servidor1`

🤖 Bot funcionando 24/7!"""

    await update.message.reply_text(mensagem,
                                    parse_mode='Markdown',
                                    reply_markup=criar_teclado_principal())

@verificar_admin
async def lidar_com_botoes(update, context):
    """Lida com os botões pressionados - somente quando não há conversa ativa"""
    texto = update.message.text

    # Lista de botões reconhecidos
    botoes_reconhecidos = [
        "👥 Listar Clientes", "➕ Adicionar Cliente", "📊 Relatórios",
        "🔍 Buscar Cliente", "🏢 Empresa", "💳 PIX", "📞 Suporte",
        "📱 WhatsApp Status", "🧪 Testar WhatsApp", "📱 QR Code",
        "⚙️ Gerenciar WhatsApp", "📄 Templates", "⏰ Agendador",
        "📋 Fila de Mensagens", "📜 Logs de Envios", "❓ Ajuda"
    ]

    # Se não é um botão reconhecido, não fazer nada (evitar mensagem de ajuda)
    if texto not in botoes_reconhecidos:
        return

    # Verificar se há uma conversa ativa (ConversationHandler em uso)
    if hasattr(context, 'user_data') and context.user_data:
        # Se há dados de conversa ativa, não processar aqui
        if any(key in context.user_data for key in
               ['editando_cliente_id', 'cadastro_atual', 'config_estado']):
            return

    if texto == "👥 Listar Clientes":
        await listar_clientes(update, context)
    elif texto == "➕ Adicionar Cliente":
        # Este caso será tratado pelo ConversationHandler
        pass
    elif texto == "📊 Relatórios":
        await relatorio(update, context)
    elif texto == "🔍 Buscar Cliente":
        await buscar_cliente_cmd(update, context)
    elif texto == "🏢 Empresa":
        # Este caso será tratado pelo ConversationHandler config_direct_handler
        pass
    elif texto == "💳 PIX":
        # Este caso será tratado pelo ConversationHandler config_direct_handler
        pass
    elif texto == "📞 Suporte":
        # Este caso será tratado pelo ConversationHandler config_direct_handler
        pass
    elif texto == "📱 WhatsApp Status":
        await whatsapp_status_direct(update, context)
    elif texto == "🧪 Testar WhatsApp":
        await testar_whatsapp_direct(update, context)
    elif texto == "📱 QR Code":
        await qr_code_direct(update, context)
    elif texto == "⚙️ Gerenciar WhatsApp":
        await gerenciar_whatsapp_direct(update, context)
    elif texto == "📄 Templates":
        await menu_templates(update, context)
    elif texto == "⏰ Agendador":
        await menu_agendador(update, context)
    elif texto == "📋 Fila de Mensagens":
        await fila_mensagens(update, context)
    elif texto == "📜 Logs de Envios":
        await logs_envios(update, context)
    elif texto == "❓ Ajuda":
        await help_cmd(update, context)

@verificar_admin
async def buscar_cliente_cmd(update, context):
    """Comando para buscar cliente"""
    await update.message.reply_text(
        "🔍 *Buscar Cliente*\n\n"
        "Para buscar um cliente, use:\n"
        "`/buscar telefone`\n\n"
        "*Exemplo:*\n"
        "`/buscar 11999999999`",
        parse_mode='Markdown',
        reply_markup=criar_teclado_principal())

@verificar_admin
async def buscar_cliente(update, context):
    """Busca cliente por telefone"""
    try:
        if not context.args:
            await update.message.reply_text(
                "❌ Por favor, informe o telefone!\n\n"
                "Exemplo: `/buscar 11999999999`",
                parse_mode='Markdown',
                reply_markup=criar_teclado_principal())
            return

        telefone = context.args[0]

        from database import DatabaseManager
        db = DatabaseManager()
        cliente = db.buscar_cliente_por_telefone(telefone)

        if not cliente:
            await update.message.reply_text(
                f"❌ Cliente com telefone {telefone} não encontrado.",
                reply_markup=criar_teclado_principal())
            return

        vencimento = datetime.strptime(cliente['vencimento'], '%Y-%m-%d')

        mensagem = f"""👤 *Cliente Encontrado*

📝 *Nome:* {cliente['nome']}
📱 *Telefone:* {cliente['telefone']}
📦 *Pacote:* {cliente['pacote']}
💰 *Valor:* R$ {cliente['plano']:.2f}
📅 *Vencimento:* {vencimento.strftime('%d/%m/%Y')}
🖥️ *Servidor:* {cliente['servidor']}"""

        await update.message.reply_text(mensagem,
                                        parse_mode='Markdown',
                                        reply_markup=criar_teclado_principal())

    except Exception as e:
        logger.error(f"Erro ao buscar cliente: {e}")
        await update.message.reply_text("❌ Erro ao buscar cliente!",
                                        reply_markup=criar_teclado_principal())

@verificar_admin
async def configuracoes_cmd(update, context):
    """Comando de configurações"""
    try:
        from database import DatabaseManager
        db = DatabaseManager()
        config = db.get_configuracoes()

        if config:
            # Escapar caracteres especiais para HTML
            empresa = escapar_html(config['empresa_nome'])
            pix_key = escapar_html(config['pix_key'])
            suporte = escapar_html(config['contato_suporte'])

            mensagem = f"""⚙️ <b>Configurações Atuais</b>

🏢 <b>Empresa:</b> {empresa}
💳 <b>PIX:</b> {pix_key}
📞 <b>Suporte:</b> {suporte}"""

            # Criar botões inline para editar configurações
            keyboard = [
                [
                    InlineKeyboardButton("🏢 Alterar Empresa",
                                         callback_data="config_empresa")
                ],
                [
                    InlineKeyboardButton("💳 Alterar PIX",
                                         callback_data="config_pix")
                ],
                [
                    InlineKeyboardButton("📞 Alterar Suporte",
                                         callback_data="config_suporte")
                ],
                [
                    InlineKeyboardButton("🔄 Atualizar",
                                         callback_data="config_refresh")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

        else:
            mensagem = """⚙️ <b>Configurações</b>

Nenhuma configuração encontrada.
Configure sua empresa para personalizar as mensagens do bot."""

            # Botões para configuração inicial
            keyboard = [
                [
                    InlineKeyboardButton("🏢 Configurar Empresa",
                                         callback_data="config_empresa")
                ],
                [
                    InlineKeyboardButton("💳 Configurar PIX",
                                         callback_data="config_pix")
                ],
                [
                    InlineKeyboardButton("📞 Configurar Suporte",
                                         callback_data="config_suporte")
                ],
                [
                    InlineKeyboardButton("📱 Status WhatsApp",
                                         callback_data="whatsapp_status")
                ],
                [
                    InlineKeyboardButton("🧪 Testar WhatsApp",
                                         callback_data="whatsapp_test")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(mensagem,
                                        parse_mode='HTML',
                                        reply_markup=reply_markup)

    except Exception as e:
        logger.error(f"Erro nas configurações: {e}")
        await update.message.reply_text("❌ Erro ao carregar configurações!",
                                        reply_markup=criar_teclado_principal())

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())

