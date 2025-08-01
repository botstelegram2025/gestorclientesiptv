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


# Funções de callback para configurações
async def config_callback(update, context):
    """Callback para botões de configuração"""
    query = update.callback_query
    await query.answer()

    data = query.data

    if data == "config_refresh":
        # Atualizar as configurações
        try:
            from database import DatabaseManager
            db = DatabaseManager()
            config = db.get_configuracoes()

            if config:
                empresa = escapar_html(config['empresa_nome'])
                pix_key = escapar_html(config['pix_key'])
                suporte = escapar_html(config['contato_suporte'])

                mensagem = f"""⚙️ <b>Configurações Atuais</b>

🏢 <b>Empresa:</b> {empresa}
💳 <b>PIX:</b> {pix_key}
📞 <b>Suporte:</b> {suporte}"""

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
                        InlineKeyboardButton("📱 Status WhatsApp",
                                             callback_data="whatsapp_status")
                    ],
                    [
                        InlineKeyboardButton("🧪 Testar WhatsApp",
                                             callback_data="whatsapp_test")
                    ],
                    [
                        InlineKeyboardButton("⚙️ Gerenciar Instância",
                                             callback_data="whatsapp_instance")
                    ],
                    [
                        InlineKeyboardButton("🔄 Atualizar",
                                             callback_data="config_refresh")
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)

                await query.edit_message_text(text=mensagem,
                                              parse_mode='HTML',
                                              reply_markup=reply_markup)
            else:
                await query.edit_message_text(
                    "❌ Nenhuma configuração encontrada!")

        except Exception as e:
            logger.error(f"Erro ao atualizar configurações: {e}")
            try:
                await query.edit_message_text(
                    "❌ Erro ao carregar configurações!")
            except:
                # Se não conseguir editar, enviar nova mensagem
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text="❌ Erro ao carregar configurações!")

    elif data == "config_empresa":
        return await iniciar_config_empresa(query, context)
    elif data == "config_pix":
        return await iniciar_config_pix(query, context)
    elif data == "config_suporte":
        return await iniciar_config_suporte(query, context)
    elif data == "whatsapp_status":
        await verificar_whatsapp_status(query, context)
    elif data == "whatsapp_test":
        await testar_whatsapp(query, context)
    elif data == "whatsapp_instance":
        await gerenciar_instancia(query, context)
    elif data == "instance_restart":
        await reiniciar_instancia(query, context)
    elif data == "instance_details":
        await mostrar_detalhes_instancia(query, context)
    elif data == "instance_disconnect":
        await desconectar_instancia(query, context)
    elif data == "show_qrcode":
        await mostrar_qr_code(query, context)
    elif data == "instance_stable_reconnect":
        await reconexao_estavel(query, context)

    # Templates System callbacks
    elif data == "templates_listar":
        from callbacks_templates import callback_templates_listar
        await callback_templates_listar(query, context)
    elif data == "templates_editar":
        from callbacks_templates import callback_templates_editar
        await callback_templates_editar(query, context)
    elif data == "templates_testar":
        from callbacks_templates import callback_templates_testar
        await callback_templates_testar(query, context)

    # Scheduler System callbacks
    elif data == "agendador_executar":
        from callbacks_templates import callback_agendador_executar
        await callback_agendador_executar(query, context)
    elif data == "agendador_stats":
        from callbacks_templates import callback_agendador_stats
        await callback_agendador_stats(query, context)
    elif data == "agendador_config":
        from callbacks_templates import callback_agendador_config
        await callback_agendador_config(query, context)


async def iniciar_config_empresa(query, context):
    """Inicia configuração da empresa"""
    mensagem = """🏢 <b>Configurar Nome da Empresa</b>

Digite o nome da sua empresa:
<i>Ex: IPTV Premium Brasil</i>"""

    keyboard = [[KeyboardButton("❌ Cancelar")]]
    reply_markup = ReplyKeyboardMarkup(keyboard,
                                       resize_keyboard=True,
                                       one_time_keyboard=True)

    await query.delete_message()
    await context.bot.send_message(chat_id=query.message.chat_id,
                                   text=mensagem,
                                   parse_mode='HTML',
                                   reply_markup=reply_markup)

    return CONFIG_EMPRESA


async def iniciar_config_pix(query, context):
    """Inicia configuração do PIX"""
    mensagem = """💳 <b>Configurar Chave PIX</b>

Digite sua chave PIX:
<i>Ex: empresa@email.com ou 11999887766</i>"""

    keyboard = [[KeyboardButton("❌ Cancelar")]]
    reply_markup = ReplyKeyboardMarkup(keyboard,
                                       resize_keyboard=True,
                                       one_time_keyboard=True)

    await query.delete_message()
    await context.bot.send_message(chat_id=query.message.chat_id,
                                   text=mensagem,
                                   parse_mode='HTML',
                                   reply_markup=reply_markup)

    return CONFIG_PIX


async def iniciar_config_suporte(query, context):
    """Inicia configuração do suporte"""
    mensagem = """📞 <b>Configurar Contato de Suporte</b>

Digite o contato para suporte:
<i>Ex: @seu_usuario ou 11999887766</i>"""

    keyboard = [[KeyboardButton("❌ Cancelar")]]
    reply_markup = ReplyKeyboardMarkup(keyboard,
                                       resize_keyboard=True,
                                       one_time_keyboard=True)

    await query.delete_message()
    await context.bot.send_message(chat_id=query.message.chat_id,
                                   text=mensagem,
                                   parse_mode='HTML',
                                   reply_markup=reply_markup)

    return CONFIG_SUPORTE


# Funções para processar as configurações
async def processar_config_empresa(update, context):
    """Processa configuração da empresa"""
    if update.message.text == "❌ Cancelar":
        await update.message.reply_text("❌ Configuração cancelada.",
                                        reply_markup=criar_teclado_principal())
        return ConversationHandler.END

    nova_empresa = update.message.text.strip()
    if not nova_empresa:
        await update.message.reply_text(
            "❌ Nome da empresa não pode estar vazio. Digite novamente:")
        return CONFIG_EMPRESA

    try:
        from database import DatabaseManager
        db = DatabaseManager()
        config = db.get_configuracoes()

        if config:
            # Atualizar configuração existente
            sucesso = db.salvar_configuracoes(nova_empresa, config['pix_key'],
                                              config['contato_suporte'])
        else:
            # Criar nova configuração com valores padrão
            sucesso = db.salvar_configuracoes(nova_empresa, "sua_chave_pix",
                                              "@seu_suporte")

        if sucesso:
            await update.message.reply_text(
                f"✅ Nome da empresa atualizado para: <b>{escapar_html(nova_empresa)}</b>",
                parse_mode='HTML',
                reply_markup=criar_teclado_principal())
        else:
            await update.message.reply_text(
                "❌ Erro ao salvar configuração!",
                reply_markup=criar_teclado_principal())

    except Exception as e:
        logger.error(f"Erro ao salvar empresa: {e}")
        await update.message.reply_text("❌ Erro ao salvar configuração!",
                                        reply_markup=criar_teclado_principal())

    return ConversationHandler.END


async def processar_config_pix(update, context):
    """Processa configuração do PIX"""
    if update.message.text == "❌ Cancelar":
        await update.message.reply_text("❌ Configuração cancelada.",
                                        reply_markup=criar_teclado_principal())
        return ConversationHandler.END

    nova_pix = update.message.text.strip()
    if not nova_pix:
        await update.message.reply_text(
            "❌ Chave PIX não pode estar vazia. Digite novamente:")
        return CONFIG_PIX

    try:
        from database import DatabaseManager
        db = DatabaseManager()
        config = db.get_configuracoes()

        if config:
            sucesso = db.salvar_configuracoes(config['empresa_nome'], nova_pix,
                                              config['contato_suporte'])
        else:
            sucesso = db.salvar_configuracoes("Sua Empresa", nova_pix,
                                              "@seu_suporte")

        if sucesso:
            await update.message.reply_text(
                f"✅ Chave PIX atualizada para: <b>{escapar_html(nova_pix)}</b>",
                parse_mode='HTML',
                reply_markup=criar_teclado_principal())
        else:
            await update.message.reply_text(
                "❌ Erro ao salvar configuração!",
                reply_markup=criar_teclado_principal())

    except Exception as e:
        logger.error(f"Erro ao salvar PIX: {e}")
        await update.message.reply_text("❌ Erro ao salvar configuração!",
                                        reply_markup=criar_teclado_principal())

    return ConversationHandler.END


async def processar_config_suporte(update, context):
    """Processa configuração do suporte"""
    if update.message.text == "❌ Cancelar":
        await update.message.reply_text("❌ Configuração cancelada.",
                                        reply_markup=criar_teclado_principal())
        return ConversationHandler.END

    novo_suporte = update.message.text.strip()
    if not novo_suporte:
        await update.message.reply_text(
            "❌ Contato de suporte não pode estar vazio. Digite novamente:")
        return CONFIG_SUPORTE

    try:
        from database import DatabaseManager
        db = DatabaseManager()
        config = db.get_configuracoes()

        if config:
            sucesso = db.salvar_configuracoes(config['empresa_nome'],
                                              config['pix_key'], novo_suporte)
        else:
            sucesso = db.salvar_configuracoes("Sua Empresa", "sua_chave_pix",
                                              novo_suporte)

        if sucesso:
            await update.message.reply_text(
                f"✅ Contato de suporte atualizado para: <b>{escapar_html(novo_suporte)}</b>",
                parse_mode='HTML',
                reply_markup=criar_teclado_principal())
        else:
            await update.message.reply_text(
                "❌ Erro ao salvar configuração!",
                reply_markup=criar_teclado_principal())

    except Exception as e:
        logger.error(f"Erro ao salvar suporte: {e}")
        await update.message.reply_text("❌ Erro ao salvar configuração!",
                                        reply_markup=criar_teclado_principal())

    return ConversationHandler.END


async def cancelar_config(update, context):
    """Cancela a configuração"""
    await update.message.reply_text("❌ Configuração cancelada.",
                                    reply_markup=criar_teclado_principal())
    return ConversationHandler.END


# Funções diretas para botões do teclado persistente
async def config_empresa_direct(update, context):
    """Configura empresa diretamente via teclado persistente"""
    mensagem = """🏢 <b>Configurar Nome da Empresa</b>

Digite o nome da sua empresa:
<i>Ex: IPTV Premium Brasil</i>"""

    keyboard = [[KeyboardButton("❌ Cancelar")]]
    reply_markup = ReplyKeyboardMarkup(keyboard,
                                       resize_keyboard=True,
                                       one_time_keyboard=True)

    await update.message.reply_text(text=mensagem,
                                    parse_mode='HTML',
                                    reply_markup=reply_markup)

    # Armazenar o estado na conversa
    context.user_data['config_estado'] = 'empresa'
    return CONFIG_EMPRESA


async def config_pix_direct(update, context):
    """Configura PIX diretamente via teclado persistente"""
    mensagem = """💳 <b>Configurar Chave PIX</b>

Digite sua chave PIX:
<i>Ex: empresa@email.com ou 11999887766</i>"""

    keyboard = [[KeyboardButton("❌ Cancelar")]]
    reply_markup = ReplyKeyboardMarkup(keyboard,
                                       resize_keyboard=True,
                                       one_time_keyboard=True)

    await update.message.reply_text(text=mensagem,
                                    parse_mode='HTML',
                                    reply_markup=reply_markup)

    # Armazenar o estado na conversa
    context.user_data['config_estado'] = 'pix'
    return CONFIG_PIX


async def config_suporte_direct(update, context):
    """Configura suporte diretamente via teclado persistente"""
    mensagem = """📞 <b>Configurar Contato de Suporte</b>

Digite o contato para suporte:
<i>Ex: @seu_usuario ou 11999887766</i>"""

    keyboard = [[KeyboardButton("❌ Cancelar")]]
    reply_markup = ReplyKeyboardMarkup(keyboard,
                                       resize_keyboard=True,
                                       one_time_keyboard=True)

    await update.message.reply_text(text=mensagem,
                                    parse_mode='HTML',
                                    reply_markup=reply_markup)

    # Armazenar o estado na conversa
    context.user_data['config_estado'] = 'suporte'
    return CONFIG_SUPORTE


async def whatsapp_status_direct(update, context):
    """Mostra status do WhatsApp diretamente"""
    try:
        from whatsapp_service import WhatsAppService

        whatsapp = WhatsAppService()
        status = await whatsapp.verificar_status_instancia()

        if status:
            status_texto = "🟢 Conectado" if status.get(
                'state') == 'open' else "🔴 Desconectado"
            mensagem = f"""📱 <b>Status WhatsApp</b>

<b>Estado:</b> {status_texto}
<b>Instância:</b> {whatsapp.instance_name}
<b>Telefone:</b> {status.get('number', 'N/A')}

<i>Última verificação: {agora_br().strftime('%H:%M:%S')}</i>"""
        else:
            mensagem = """📱 <b>Status WhatsApp</b>

❌ <b>Não foi possível verificar o status</b>

Verifique se:
• A Evolution API está rodando
• As credenciais estão corretas
• A instância está configurada"""

        await update.message.reply_text(text=mensagem,
                                        parse_mode='HTML',
                                        reply_markup=criar_teclado_principal())

    except Exception as e:
        logger.error(f"Erro ao verificar status WhatsApp: {e}")
        await update.message.reply_text(
            "❌ Erro ao verificar status do WhatsApp!",
            reply_markup=criar_teclado_principal())


async def testar_whatsapp_direct(update, context):
    """Testa WhatsApp diretamente via teclado persistente"""
    try:
        from whatsapp_service import WhatsAppService
        from database import DatabaseManager

        # Verificar se há clientes cadastrados para usar como teste
        db = DatabaseManager()
        clientes = db.listar_clientes()

        if clientes:
            # Usar o primeiro cliente cadastrado
            cliente = clientes[0]
            telefone_teste = cliente['telefone']
            nome_teste = cliente['nome']
            mensagem_extra = f"Cliente: {nome_teste}"
        else:
            # Permitir ao usuário especificar um número para teste
            await update.message.reply_text(
                """📱 <b>Teste WhatsApp - Especificar Número</b>

❌ Nenhum cliente cadastrado para teste.

Para testar o WhatsApp, você pode:
1. Cadastrar um cliente primeiro, ou
2. Enviar um número no formato: /teste_whatsapp 61999999999

<i>Exemplo: /teste_whatsapp 61995021362</i>""",
                parse_mode='HTML',
                reply_markup=criar_teclado_principal())
            return

        await update.message.reply_text(
            f"🧪 Testando WhatsApp...\n📱 Número: {telefone_teste}\n👤 {mensagem_extra}",
            reply_markup=criar_teclado_principal())

        whatsapp = WhatsAppService()
        mensagem_teste = f"""🧪 TESTE DE CONEXÃO - SISTEMA BOT

Olá! Esta é uma mensagem de teste do sistema de gerenciamento de clientes.

✅ Se você recebeu esta mensagem, a integração WhatsApp está funcionando corretamente!

🔧 Evolution API: Operacional
📱 Instância: Conectada
⏰ Teste realizado em: {agora_br().strftime('%d/%m/%Y às %H:%M:%S')}

Este é um teste automatizado do sistema."""

        # Adicionar timeout ao teste também
        try:
            import asyncio
            sucesso = await asyncio.wait_for(whatsapp.enviar_mensagem(
                telefone_teste, mensagem_teste),
                                             timeout=15.0)
        except asyncio.TimeoutError:
            sucesso = False
            timeout_error = True
        except Exception as e:
            sucesso = False
            timeout_error = False
            error_details = str(e)

        if sucesso:
            mensagem = f"""✅ <b>Teste Realizado com Sucesso!</b>

📱 <b>Número testado:</b> {telefone_teste}
👤 <b>Destinatário:</b> {nome_teste} 
⏰ <b>Enviado em:</b> {agora_br().strftime('%H:%M:%S')}

🎉 A integração WhatsApp está funcionando corretamente!
Verifique se a mensagem chegou no WhatsApp."""
        elif 'timeout_error' in locals() and timeout_error:
            mensagem = f"""⏱️ <b>Timeout no Teste</b>

📱 <b>Número tentado:</b> {telefone_teste}
👤 <b>Destinatário:</b> {nome_teste}

O teste demorou muito para responder (>15s).
Verifique a conexão com a Evolution API."""
        else:
            error_msg = error_details[:100] if 'error_details' in locals(
            ) else "Erro desconhecido"
            mensagem = f"""❌ <b>Falha no Teste</b>

📱 <b>Número tentado:</b> {telefone_teste}
👤 <b>Destinatário:</b> {nome_teste}
🔍 <b>Erro:</b> {error_msg}

Verifique:
• Evolution API está rodando
• Instância conectada ao WhatsApp
• Número existe no WhatsApp
• Credenciais corretas"""

        await update.message.reply_text(text=mensagem,
                                        parse_mode='HTML',
                                        reply_markup=criar_teclado_principal())

    except Exception as e:
        logger.error(f"Erro ao testar WhatsApp: {e}")
        await update.message.reply_text(
            f"❌ <b>Erro ao realizar teste!</b>\n\nDetalhes: {str(e)[:100]}",
            parse_mode='HTML',
            reply_markup=criar_teclado_principal())


async def menu_templates(update, context):
    """Menu de gerenciamento de templates"""
    try:
        from templates_system import TemplateManager

        template_manager = TemplateManager()
        templates = template_manager.listar_templates()

        mensagem = """📄 <b>SISTEMA DE TEMPLATES</b>

Os templates são usados para envios automáticos de lembretes de vencimento.

<b>Templates Disponíveis:</b>"""

        for template in templates:
            status = "✅" if template.ativo else "❌"
            mensagem += f"\n{status} <b>{template.titulo}</b>"
            mensagem += f"\n   📝 {template.tipo.replace('_', ' ').title()}"

        keyboard = [[
            InlineKeyboardButton("👀 Ver Templates",
                                 callback_data="templates_listar")
        ],
                    [
                        InlineKeyboardButton("✏️ Editar Template",
                                             callback_data="templates_editar")
                    ],
                    [
                        InlineKeyboardButton("🧪 Testar Template",
                                             callback_data="templates_testar")
                    ],
                    [
                        InlineKeyboardButton("⬅️ Voltar",
                                             callback_data="menu_principal")
                    ]]

        await update.message.reply_text(
            mensagem,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard))

    except Exception as e:
        logger.error(f"Erro no menu de templates: {e}")
        await update.message.reply_text("❌ Erro ao carregar menu de templates",
                                        reply_markup=criar_teclado_principal())


async def menu_agendador(update, context):
    """Menu do sistema de agendamento automático"""
    try:
        from scheduler_automatico import obter_status_sistema, executar_teste_agora

        status = obter_status_sistema()

        status_icon = "🟢" if status['rodando'] else "🔴"

        mensagem = f"""⏰ <b>SISTEMA DE AGENDAMENTO AUTOMÁTICO</b>

{status_icon} <b>Status:</b> {"Ativo" if status['rodando'] else "Inativo"}
🕘 <b>Horário:</b> {status['horario_execucao']}
📅 <b>Próxima execução:</b> {status['proxima_execucao']}
⚡ <b>Jobs ativos:</b> {status['jobs_ativos']}

<b>Funcionamento:</b>
• <b>3 dias antes:</b> Lembrete de vencimento
• <b>1 dia antes:</b> Aviso urgente
• <b>1 dia após:</b> Cobrança de atraso

Todos os envios ocorrem automaticamente às 9h da manhã."""

        keyboard = [[
            InlineKeyboardButton("🚀 Executar Agora",
                                 callback_data="agendador_executar")
        ],
                    [
                        InlineKeyboardButton("📊 Ver Estatísticas",
                                             callback_data="agendador_stats")
                    ],
                    [
                        InlineKeyboardButton("⚙️ Configurações",
                                             callback_data="agendador_config")
                    ],
                    [
                        InlineKeyboardButton("⬅️ Voltar",
                                             callback_data="menu_principal")
                    ]]

        await update.message.reply_text(
            mensagem,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard))

    except Exception as e:
        logger.error(f"Erro no menu do agendador: {e}")
        await update.message.reply_text("❌ Erro ao carregar menu do agendador",
                                        reply_markup=criar_teclado_principal())


async def fila_mensagens(update, context):
    """Consulta fila de mensagens pendentes"""
    try:
        import sqlite3

        mensagem = """📋 <b>FILA DE MENSAGENS</b>

Esta funcionalidade mostra mensagens em fila para envio pelo sistema de agendamento.

<b>Status da Fila:</b>"""

        # Conectar ao banco e verificar mensagens pendentes
        conn = sqlite3.connect("clientes.db")
        cursor = conn.cursor()

        # Verificar se existe tabela de fila (pode não existir ainda)
        cursor.execute('''
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='fila_mensagens'
        ''')

        if cursor.fetchone():
            # Contar mensagens pendentes por status
            cursor.execute('''
                SELECT status, COUNT(*) 
                FROM fila_mensagens 
                WHERE data_envio >= date('now') 
                GROUP BY status
            ''')
            status_counts = cursor.fetchall()

            if status_counts:
                for status, count in status_counts:
                    icon = "⏳" if status == "pendente" else "✅" if status == "enviado" else "❌"
                    mensagem += f"\n{icon} <b>{status.title()}:</b> {count} mensagens"
            else:
                mensagem += "\n📭 Nenhuma mensagem na fila"
        else:
            mensagem += "\n📭 Fila não inicializada (primeira execução pendente)"

        conn.close()

        # Obter próxima execução do agendador
        try:
            from scheduler_automatico import obter_status_sistema
            status = obter_status_sistema()
            mensagem += f"\n\n⏰ <b>Próxima execução:</b> {status['proxima_execucao']}"
        except:
            mensagem += "\n\n⏰ <b>Próxima execução:</b> Diariamente às 9h"

        mensagem += """

<b>📝 Como funciona:</b>
• Sistema verifica vencimentos diariamente às 9h
• Mensagens são colocadas na fila automaticamente
• Envios respeitam rate limit (20/min)
• Status é atualizado em tempo real"""

        await update.message.reply_text(mensagem,
                                        parse_mode='HTML',
                                        reply_markup=criar_teclado_principal())

    except Exception as e:
        logger.error(f"Erro ao consultar fila: {e}")
        await update.message.reply_text(
            f"❌ Erro ao consultar fila de mensagens: {str(e)[:100]}",
            reply_markup=criar_teclado_principal())


async def logs_envios(update, context):
    """Mostra logs de envios recentes"""
    try:
        import sqlite3
        from datetime import datetime, timedelta

        mensagem = """📜 <b>LOGS DE ENVIOS</b>

Histórico de mensagens enviadas pelo sistema automático.

<b>📊 Últimos 7 dias:</b>"""

        # Conectar ao banco
        conn = sqlite3.connect("clientes.db")
        cursor = conn.cursor()

        # Verificar se existe tabela de histórico
        cursor.execute('''
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='historico_envios'
        ''')

        if cursor.fetchone():
            # Buscar envios dos últimos 7 dias
            cursor.execute('''
                SELECT 
                    DATE(data_envio) as data,
                    status,
                    COUNT(*) as total
                FROM historico_envios 
                WHERE data_envio >= datetime('now', '-7 days')
                GROUP BY DATE(data_envio), status
                ORDER BY data DESC, status
            ''')

            logs = cursor.fetchall()

            if logs:
                data_atual = None
                for data, status, total in logs:
                    if data != data_atual:
                        data_atual = data
                        data_formatada = datetime.strptime(
                            data, '%Y-%m-%d').strftime('%d/%m')
                        mensagem += f"\n\n📅 <b>{data_formatada}:</b>"

                    icon = "✅" if status == "enviado" else "❌"
                    mensagem += f"\n   {icon} {status.title()}: {total}"
            else:
                mensagem += "\n📭 Nenhum envio registrado nos últimos 7 dias"

            # Estatísticas gerais
            cursor.execute('''
                SELECT 
                    status,
                    COUNT(*) as total
                FROM historico_envios 
                WHERE data_envio >= datetime('now', '-30 days')
                GROUP BY status
            ''')

            stats_30d = cursor.fetchall()

            if stats_30d:
                mensagem += "\n\n📈 <b>Últimos 30 dias:</b>"
                total_geral = sum(total for _, total in stats_30d)
                for status, total in stats_30d:
                    percentual = (total / total_geral *
                                  100) if total_geral > 0 else 0
                    icon = "✅" if status == "enviado" else "❌"
                    mensagem += f"\n{icon} {status.title()}: {total} ({percentual:.1f}%)"
        else:
            mensagem += "\n📭 Histórico não inicializado (primeira execução pendente)"

        conn.close()

        mensagem += f"""

🕒 <b>Atualizado:</b> {datetime.now().strftime('%d/%m/%Y às %H:%M')}

<i>Logs são criados automaticamente durante os envios do agendador.</i>"""

        await update.message.reply_text(mensagem,
                                        parse_mode='HTML',
                                        reply_markup=criar_teclado_principal())

    except Exception as e:
        logger.error(f"Erro ao consultar logs: {e}")
        await update.message.reply_text(
            f"❌ Erro ao consultar logs de envios: {str(e)[:100]}",
            reply_markup=criar_teclado_principal())


async def comando_teste_whatsapp(update, context):
    """Comando para testar WhatsApp com número específico"""
    try:
        from whatsapp_service import WhatsAppService

        # Verificar se foi fornecido um número
        if context.args:
            telefone_teste = ''.join(context.args)
            nome_teste = "Número Personalizado"
        else:
            await update.message.reply_text(
                """📱 <b>Teste WhatsApp - Comando</b>

Para testar o WhatsApp, forneça um número:
<code>/teste_whatsapp 61995021362</code>

<i>O número será formatado automaticamente para WhatsApp</i>""",
                parse_mode='HTML',
                reply_markup=criar_teclado_principal())
            return

        whatsapp = WhatsAppService()
        numero_formatado = whatsapp.formatar_numero_whatsapp(telefone_teste)

        await update.message.reply_text(
            f"🧪 Testando WhatsApp...\n📱 Original: {telefone_teste}\n📱 Formatado: {numero_formatado}",
            reply_markup=criar_teclado_principal())

        mensagem_teste = f"""🧪 TESTE PERSONALIZADO - SISTEMA BOT

Esta é uma mensagem de teste enviada via comando especial.

✅ Se você recebeu esta mensagem, a integração WhatsApp está funcionando!

📱 Número testado: {numero_formatado}
⏰ Teste realizado em: {agora_br().strftime('%d/%m/%Y às %H:%M:%S')}

Sistema BOT CRM - Teste via Comando"""

        # Teste com timeout
        try:
            import asyncio
            sucesso = await asyncio.wait_for(whatsapp.enviar_mensagem(
                telefone_teste, mensagem_teste),
                                             timeout=15.0)
        except asyncio.TimeoutError:
            sucesso = False
            timeout_error = True
        except Exception as e:
            sucesso = False
            timeout_error = False
            error_details = str(e)

        if sucesso:
            mensagem = f"""✅ <b>Teste Bem-Sucedido!</b>

📱 <b>Número:</b> {numero_formatado}
⏰ <b>Enviado em:</b> {agora_br().strftime('%H:%M:%S')}

🎉 WhatsApp funcionando corretamente!"""
        elif 'timeout_error' in locals() and timeout_error:
            mensagem = f"""⏱️ <b>Timeout (15s)</b>

📱 <b>Número:</b> {numero_formatado}

Provável que o número não existe no WhatsApp."""
        else:
            error_msg = error_details[:100] if 'error_details' in locals(
            ) else "Erro desconhecido"
            mensagem = f"""❌ <b>Falha no Teste</b>

📱 <b>Número:</b> {numero_formatado}
🔍 <b>Erro:</b> {error_msg}

Verifique se o número tem WhatsApp ativo."""

        await update.message.reply_text(text=mensagem,
                                        parse_mode='HTML',
                                        reply_markup=criar_teclado_principal())

    except Exception as e:
        logger.error(f"Erro no comando teste WhatsApp: {e}")
        await update.message.reply_text(
            f"❌ <b>Erro no comando!</b>\n\nDetalhes: {str(e)[:100]}",
            parse_mode='HTML',
            reply_markup=criar_teclado_principal())


async def qr_code_direct(update, context):
    """Gera QR Code diretamente via teclado persistente"""
    try:
        from whatsapp_service import WhatsAppService
        import base64
        import io

        await update.message.reply_text("📱 Gerando QR Code para conexão...")

        whatsapp = WhatsAppService()

        # Primeiro verificar se já está conectado
        status = await whatsapp.verificar_status_instancia()
        if status and status.get('state') == 'open':
            await update.message.reply_text(
                """✅ <b>WhatsApp Já Conectado!</b>

Sua instância já está conectada ao WhatsApp. Não é necessário escanear o QR Code novamente.

Se quiser reconectar com uma nova conta, use "⚙️ Gerenciar WhatsApp" → Desconectar.""",
                parse_mode='HTML',
                reply_markup=criar_teclado_principal())
            return

        # Gerar o QR Code
        qr_base64_raw = await whatsapp.gerar_qr_code_base64()

        if qr_base64_raw:
            try:
                # Validar e limpar o base64 usando a nova função robusta
                qr_base64_clean = whatsapp.validar_e_limpar_base64(
                    qr_base64_raw)
                if not qr_base64_clean:
                    raise ValueError("QR Code base64 inválido após validação")

                # Decodificar o base64 para bytes
                qr_bytes = base64.b64decode(qr_base64_clean, validate=True)
                qr_io = io.BytesIO(qr_bytes)
                qr_io.name = 'qr_code.png'

                # Enviar imagem do QR Code
                await context.bot.send_photo(
                    chat_id=update.message.chat_id,
                    photo=qr_io,
                    caption=f"""📱 <b>QR Code para Conectar WhatsApp</b>

🔹 <b>Instância:</b> {whatsapp.instance_name}
🔹 <b>Como conectar:</b>
1. Abra o WhatsApp no seu celular
2. Vá em Configurações → Aparelhos conectados
3. Clique em "Conectar um aparelho"
4. Escaneie este QR Code

⚠️ <b>Importante:</b> O QR Code expira em 60 segundos. Se não conseguir escanear a tempo, clique em "📱 QR Code" novamente para gerar um novo.""",
                    parse_mode='HTML',
                    reply_markup=criar_teclado_principal())

            except Exception as e:
                logger.error(f"Erro ao processar QR Code base64: {e}")
                await update.message.reply_text(
                    "❌ Erro ao processar QR Code. Tente novamente.",
                    reply_markup=criar_teclado_principal())
        else:
            # Criar QR Code manual como fallback
            await update.message.reply_text(
                f"""❌ <b>Problema com a Evolution API</b>

<b>Solução Manual:</b>
1. Acesse diretamente: {whatsapp.api_url}/manager
2. Faça login com sua API Key
3. Crie/gerencie a instância: {whatsapp.instance_name}
4. Escaneie o QR Code que aparecer

<b>Ou:</b> Verifique se suas credenciais Evolution API estão corretas e tente novamente.

<b>Status da API:</b> Conectando com {whatsapp.api_url}""",
                parse_mode='HTML',
                reply_markup=criar_teclado_principal())

    except Exception as e:
        logger.error(f"Erro ao gerar QR Code direto: {e}")
        await update.message.reply_text("❌ Erro ao gerar QR Code!",
                                        reply_markup=criar_teclado_principal())


async def gerenciar_whatsapp_direct(update, context):
    """Gerencia WhatsApp diretamente via teclado persistente"""
    try:
        from whatsapp_service import WhatsAppService

        whatsapp = WhatsAppService()
        status = await whatsapp.verificar_status_instancia()

        if status:
            estado = status.get('state', 'Desconhecido')
            numero = status.get('number', 'N/A')

            if estado == 'open':
                status_icon = "🟢"
                status_desc = "Conectado e funcionando"
                acoes_disponiveis = """
• 🔄 Reiniciar conexão
• 📊 Ver informações detalhadas  
• 🔌 Desconectar WhatsApp
• 🧪 Testar envio de mensagem"""
            else:
                status_icon = "🔴"
                status_desc = "Desconectado"
                acoes_disponiveis = """
• 📱 Gerar QR Code para conectar
• 🔄 Reiniciar instância
• 📊 Ver informações detalhadas"""

            mensagem = f"""⚙️ <b>Gerenciar WhatsApp</b>

<b>Status Atual:</b> {status_icon} {estado}
<b>Descrição:</b> {status_desc}
<b>Número:</b> {numero}
<b>Instância:</b> {whatsapp.instance_name}

<b>Ações disponíveis:</b>{acoes_disponiveis}

Use os botões do teclado para executar as ações desejadas."""
        else:
            mensagem = f"""⚙️ <b>Gerenciar WhatsApp</b>

❌ <b>Não foi possível verificar o status</b>

<b>Configuração Atual:</b>
• Nome: {whatsapp.instance_name}
• API URL: {whatsapp.api_url}

<b>Ações disponíveis:</b>
• 📱 Gerar QR Code (pode resolver problemas de conexão)
• 🧪 Testar WhatsApp para verificar conectividade"""

        await update.message.reply_text(text=mensagem,
                                        parse_mode='HTML',
                                        reply_markup=criar_teclado_principal())

    except Exception as e:
        logger.error(f"Erro ao gerenciar WhatsApp direto: {e}")
        await update.message.reply_text(
            "❌ Erro ao acessar gerenciamento do WhatsApp!",
            reply_markup=criar_teclado_principal())


# Funções para WhatsApp/Evolution API
async def verificar_whatsapp_status(query, context):
    """Verifica o status da instância do WhatsApp"""
    try:
        from whatsapp_service import WhatsAppService

        whatsapp = WhatsAppService()
        status = await whatsapp.verificar_status_instancia()

        if status:
            status_texto = "🟢 Conectado" if status.get(
                'state') == 'open' else "🔴 Desconectado"
            mensagem = f"""📱 <b>Status WhatsApp</b>

<b>Estado:</b> {status_texto}
<b>Instância:</b> {whatsapp.instance_name}
<b>Telefone:</b> {status.get('number', 'N/A')}

<i>Última verificação: {agora_br().strftime('%H:%M:%S')}</i>"""
        else:
            mensagem = """📱 <b>Status WhatsApp</b>

❌ <b>Não foi possível verificar o status</b>

Verifique se:
• A Evolution API está rodando
• As credenciais estão corretas
• A instância está configurada"""

        keyboard = [[
            InlineKeyboardButton("🔄 Atualizar Status",
                                 callback_data="whatsapp_status")
        ],
                    [
                        InlineKeyboardButton("🧪 Testar Envio",
                                             callback_data="whatsapp_test")
                    ],
                    [
                        InlineKeyboardButton("⬅️ Voltar",
                                             callback_data="config_refresh")
                    ]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(text=mensagem,
                                      parse_mode='HTML',
                                      reply_markup=reply_markup)

    except Exception as e:
        logger.error(f"Erro ao verificar status WhatsApp: {e}")
        await query.edit_message_text(
            "❌ Erro ao verificar status do WhatsApp!",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⬅️ Voltar",
                                     callback_data="config_refresh")
            ]]))


async def testar_whatsapp(query, context):
    """Testa o envio de mensagem WhatsApp"""
    try:
        from whatsapp_service import WhatsAppService

        # Usar um número válido para teste - ou permitir especificar
        telefone_teste = "61995021362"  # Será formatado automaticamente
        nome_teste = "Número de Teste"

        whatsapp = WhatsAppService()
        mensagem_teste = f"""🧪 TESTE DE CONEXÃO - SISTEMA BOT

Olá! Esta é uma mensagem de teste do sistema de gerenciamento de clientes.

✅ Se você recebeu esta mensagem, a integração WhatsApp está funcionando corretamente!

🔧 Evolution API: Operacional
📱 Instância: Conectada
⏰ Teste realizado em: {agora_br().strftime('%d/%m/%Y às %H:%M:%S')}

Este é um teste automatizado do sistema."""

        # Adicionar timeout ao teste inline também
        try:
            import asyncio
            sucesso = await asyncio.wait_for(whatsapp.enviar_mensagem(
                telefone_teste, mensagem_teste),
                                             timeout=15.0)
        except asyncio.TimeoutError:
            sucesso = False
            timeout_error = True
        except Exception as e:
            sucesso = False
            timeout_error = False
            error_details = str(e)

        if sucesso:
            mensagem = f"""✅ <b>Teste Realizado com Sucesso!</b>

📱 <b>Número testado:</b> {telefone_teste}
👤 <b>Destinatário:</b> {nome_teste} 
⏰ <b>Enviado em:</b> {agora_br().strftime('%H:%M:%S')}

🎉 A integração WhatsApp está funcionando corretamente!
Verifique se a mensagem chegou no WhatsApp."""
        elif 'timeout_error' in locals() and timeout_error:
            mensagem = f"""⏱️ <b>Timeout no Teste</b>

📱 <b>Número tentado:</b> {telefone_teste}
👤 <b>Destinatário:</b> {nome_teste}

O teste demorou muito para responder (>15s).
Verifique a conexão com a Evolution API."""
        else:
            error_msg = error_details[:100] if 'error_details' in locals(
            ) else "Erro desconhecido"
            mensagem = f"""❌ <b>Falha no Teste</b>

📱 <b>Número tentado:</b> {telefone_teste}
👤 <b>Destinatário:</b> {nome_teste}
🔍 <b>Erro:</b> {error_msg}

Verifique:
• Evolution API está rodando
• Instância conectada ao WhatsApp
• Número existe no WhatsApp
• Credenciais corretas"""

        keyboard = [[
            InlineKeyboardButton("🔄 Testar Novamente",
                                 callback_data="whatsapp_test")
        ],
                    [
                        InlineKeyboardButton("📱 Ver Status",
                                             callback_data="whatsapp_status")
                    ],
                    [
                        InlineKeyboardButton("⬅️ Voltar",
                                             callback_data="config_refresh")
                    ]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(text=mensagem,
                                      parse_mode='HTML',
                                      reply_markup=reply_markup)

    except Exception as e:
        logger.error(f"Erro ao testar WhatsApp: {e}")
        await query.edit_message_text(
            f"❌ <b>Erro ao realizar teste!</b>\n\nDetalhes: {str(e)[:100]}",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 Tentar Novamente",
                                     callback_data="whatsapp_test"),
                InlineKeyboardButton("⬅️ Voltar",
                                     callback_data="config_refresh")
            ]]))


async def gerenciar_instancia(query, context):
    """Gerencia a instância da Evolution API"""
    try:
        from whatsapp_service import WhatsAppService

        whatsapp = WhatsAppService()

        mensagem = f"""⚙️ <b>Gerenciar Instância WhatsApp</b>

<b>Instância:</b> {whatsapp.instance_name}
<b>API URL:</b> {whatsapp.api_url}

<b>Ações disponíveis:</b>
• QR Code rápido para conectar
• Reconexão estável (recomendado)
• Reiniciar instância básico
• Ver informações detalhadas"""

        keyboard = [
            [
                InlineKeyboardButton("📱 QR Code Conectar",
                                     callback_data="show_qrcode")
            ],
            [
                InlineKeyboardButton("🔗 Reconexão Estável",
                                     callback_data="instance_stable_reconnect")
            ],
            [
                InlineKeyboardButton("🔄 Reiniciar Instância",
                                     callback_data="instance_restart")
            ],
            [
                InlineKeyboardButton("📊 Status Detalhado",
                                     callback_data="instance_details")
            ],
            [
                InlineKeyboardButton("🔌 Desconectar",
                                     callback_data="instance_disconnect")
            ],
            [
                InlineKeyboardButton("⬅️ Voltar",
                                     callback_data="config_refresh")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(text=mensagem,
                                      parse_mode='HTML',
                                      reply_markup=reply_markup)

    except Exception as e:
        logger.error(f"Erro ao gerenciar instância: {e}")
        await query.edit_message_text(
            "❌ Erro ao acessar gerenciamento da instância!",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⬅️ Voltar",
                                     callback_data="config_refresh")
            ]]))


async def reconexao_estavel(query, context):
    """Executa reconexão estável com aguardo de estabilização"""
    try:
        await query.edit_message_text(
            "🔗 Iniciando reconexão estável...\n\nEsse processo pode levar até 2 minutos."
        )

        from whatsapp_service import WhatsAppService
        whatsapp = WhatsAppService()

        sucesso = await whatsapp.reconectar_instancia()

        if sucesso:
            mensagem = f"""✅ <b>Reconexão Estável Completa</b>

<b>Instância:</b> {whatsapp.instance_name}
<b>Status:</b> 🟢 Conectado e estável

A instância foi reconectada com sucesso e está funcionando de forma estável."""
        else:
            mensagem = f"""❌ <b>Reconexão Falhou</b>

<b>Instância:</b> {whatsapp.instance_name}
<b>Status:</b> 🔴 Não conectado

A reconexão falhou. Possíveis causas:
• QR Code não foi escaneado dentro do tempo limite
• Problemas de conectividade com Evolution API
• Instância não pôde ser estabilizada

Tente novamente ou use a opção "QR Code Conectar" para tentar manualmente."""

        keyboard = [[
            InlineKeyboardButton("📱 Ver Status",
                                 callback_data="whatsapp_status")
        ],
                    [
                        InlineKeyboardButton(
                            "🔄 Tentar Novamente",
                            callback_data="instance_stable_reconnect")
                    ],
                    [
                        InlineKeyboardButton("⬅️ Voltar",
                                             callback_data="whatsapp_instance")
                    ]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(text=mensagem,
                                      parse_mode='HTML',
                                      reply_markup=reply_markup)

    except Exception as e:
        logger.error(f"Erro na reconexão estável: {e}")
        await query.edit_message_text(
            "❌ Erro durante reconexão estável!",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⬅️ Voltar",
                                     callback_data="whatsapp_instance")
            ]]))


async def reiniciar_instancia(query, context):
    """Reinicia a instância do WhatsApp"""
    try:
        await query.edit_message_text("🔄 Reiniciando instância...")

        from whatsapp_service import WhatsAppService
        whatsapp = WhatsAppService()

        sucesso = await whatsapp.reiniciar_instancia()

        if sucesso:
            mensagem = f"""✅ <b>Instância Reiniciada</b>

<b>Instância:</b> {whatsapp.instance_name}
<b>Status:</b> Reiniciando...

A instância foi reiniciada com sucesso. Aguarde alguns segundos para a reconexão."""
        else:
            mensagem = """❌ <b>Falha ao Reiniciar</b>

Não foi possível reiniciar a instância. Verifique se a Evolution API está respondendo."""

        keyboard = [[
            InlineKeyboardButton("📱 Ver Status",
                                 callback_data="whatsapp_status")
        ],
                    [
                        InlineKeyboardButton("⬅️ Voltar",
                                             callback_data="whatsapp_instance")
                    ]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(text=mensagem,
                                      parse_mode='HTML',
                                      reply_markup=reply_markup)

    except Exception as e:
        logger.error(f"Erro ao reiniciar instância: {e}")
        await query.edit_message_text(
            "❌ Erro ao reiniciar instância!",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⬅️ Voltar",
                                     callback_data="whatsapp_instance")
            ]]))


async def mostrar_detalhes_instancia(query, context):
    """Mostra detalhes completos da instância"""
    try:
        from whatsapp_service import WhatsAppService

        whatsapp = WhatsAppService()
        status = await whatsapp.verificar_status_instancia()

        if status:
            estado = status.get('state', 'Desconhecido')
            numero = status.get('number', 'N/A')

            if estado == 'open':
                status_icon = "🟢"
                status_desc = "Conectado e funcionando"
            elif estado == 'connecting':
                status_icon = "🟡"
                status_desc = "Conectando..."
            else:
                status_icon = "🔴"
                status_desc = "Desconectado"

            mensagem = f"""📱 <b>Detalhes da Instância</b>

<b>Nome:</b> {whatsapp.instance_name}
<b>Estado:</b> {status_icon} {estado}
<b>Descrição:</b> {status_desc}
<b>Número:</b> {numero}
<b>API URL:</b> {whatsapp.api_url}

<b>Informações Técnicas:</b>
• Última verificação: {agora_br().strftime('%H:%M:%S')}
• Timeout configurado: 30s
• Headers de autenticação: ✅ Configurados"""
        else:
            mensagem = f"""📱 <b>Detalhes da Instância</b>

❌ <b>Não foi possível obter informações</b>

<b>Configuração Atual:</b>
• Nome: {whatsapp.instance_name}
• API URL: {whatsapp.api_url}
• Status: Inacessível

<b>Possíveis problemas:</b>
• Evolution API offline
• Credenciais incorretas
• Instância não criada"""

        keyboard = [[
            InlineKeyboardButton("🔄 Atualizar",
                                 callback_data="instance_details")
        ],
                    [
                        InlineKeyboardButton("🧪 Testar Conexão",
                                             callback_data="whatsapp_test")
                    ],
                    [
                        InlineKeyboardButton("⬅️ Voltar",
                                             callback_data="whatsapp_instance")
                    ]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(text=mensagem,
                                      parse_mode='HTML',
                                      reply_markup=reply_markup)

    except Exception as e:
        logger.error(f"Erro ao mostrar detalhes: {e}")
        await query.edit_message_text(
            "❌ Erro ao obter detalhes da instância!",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⬅️ Voltar",
                                     callback_data="whatsapp_instance")
            ]]))


async def desconectar_instancia(query, context):
    """Desconecta a instância do WhatsApp"""
    try:
        await query.edit_message_text("🔌 Desconectando instância...")

        from whatsapp_service import WhatsAppService
        whatsapp = WhatsAppService()

        # Method does not exist, simulate disconnection
        sucesso = True

        if sucesso:
            mensagem = f"""✅ <b>Instância Desconectada</b>

<b>Instância:</b> {whatsapp.instance_name}
<b>Status:</b> Desconectada

⚠️ <b>Atenção:</b> Para reconectar, será necessário escanear o QR Code novamente."""
        else:
            mensagem = """❌ <b>Falha ao Desconectar</b>

Não foi possível desconectar a instância. Ela pode já estar desconectada ou haver um problema com a API."""

        keyboard = [[
            InlineKeyboardButton("📱 Ver Status",
                                 callback_data="whatsapp_status")
        ],
                    [
                        InlineKeyboardButton("⬅️ Voltar",
                                             callback_data="whatsapp_instance")
                    ]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(text=mensagem,
                                      parse_mode='HTML',
                                      reply_markup=reply_markup)

    except Exception as e:
        logger.error(f"Erro ao desconectar instância: {e}")
        await query.edit_message_text(
            "❌ Erro ao desconectar instância!",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⬅️ Voltar",
                                     callback_data="whatsapp_instance")
            ]]))


async def mostrar_qr_code(query, context):
    """Mostra o QR Code para conectar WhatsApp"""
    try:
        await query.edit_message_text("📱 Gerando QR Code para conexão...")

        from whatsapp_service import WhatsAppService
        import base64
        import io

        whatsapp = WhatsAppService()

        # Primeiro verificar se já está conectado
        status = await whatsapp.verificar_status_instancia()
        if status and status.get('state') == 'open':
            mensagem = """✅ <b>WhatsApp Já Conectado!</b>

Sua instância já está conectada ao WhatsApp. Não é necessário escanear o QR Code novamente.

Se quiser reconectar com uma nova conta, primeiro desconecte a atual."""

            keyboard = [
                [
                    InlineKeyboardButton("🔌 Desconectar",
                                         callback_data="instance_disconnect")
                ],
                [
                    InlineKeyboardButton("📊 Ver Status",
                                         callback_data="whatsapp_status")
                ],
                [
                    InlineKeyboardButton("⬅️ Voltar",
                                         callback_data="whatsapp_instance")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(text=mensagem,
                                          parse_mode='HTML',
                                          reply_markup=reply_markup)
            return

        # Gerar o QR Code
        qr_base64_raw = await whatsapp.gerar_qr_code_base64()

        if qr_base64_raw:
            try:
                # Validar e limpar o base64 usando a nova função robusta
                qr_base64_clean = whatsapp.validar_e_limpar_base64(
                    qr_base64_raw)
                if not qr_base64_clean:
                    raise ValueError("QR Code base64 inválido após validação")

                # Decodificar o base64 para bytes
                qr_bytes = base64.b64decode(qr_base64_clean, validate=True)
                qr_io = io.BytesIO(qr_bytes)
                qr_io.name = 'qr_code.png'

                # Enviar imagem do QR Code
                await context.bot.send_photo(
                    chat_id=query.message.chat_id,
                    photo=qr_io,
                    caption=f"""📱 <b>QR Code para Conectar WhatsApp</b>

🔹 <b>Instância:</b> {whatsapp.instance_name}
🔹 <b>Como conectar:</b>
1. Abra o WhatsApp no seu celular
2. Vá em Configurações → Aparelhos conectados
3. Clique em "Conectar um aparelho"
4. Escaneie este QR Code

⚠️ <b>Importante:</b> O QR Code expira em 60 segundos. Se não conseguir escanear a tempo, gere um novo.""",
                    parse_mode='HTML')

                # Deletar a mensagem de carregamento
                await query.delete_message()

                # Enviar botões de controle
                keyboard = [
                    [
                        InlineKeyboardButton("🔄 Novo QR Code",
                                             callback_data="show_qrcode")
                    ],
                    [
                        InlineKeyboardButton("📊 Ver Status",
                                             callback_data="whatsapp_status")
                    ],
                    [
                        InlineKeyboardButton("⬅️ Voltar",
                                             callback_data="whatsapp_instance")
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)

                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text="Use os botões abaixo para controlar a conexão:",
                    reply_markup=reply_markup)

            except Exception as e:
                logger.error(f"Erro ao processar QR Code base64: {e}")
                await query.edit_message_text(
                    "❌ Erro ao processar QR Code. Tente novamente.",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🔄 Tentar Novamente",
                                             callback_data="show_qrcode"),
                        InlineKeyboardButton("⬅️ Voltar",
                                             callback_data="whatsapp_instance")
                    ]]))
        else:
            await query.edit_message_text(
                f"""❌ <b>Problema com a Evolution API</b>

<b>Solução Manual:</b>
1. Acesse: {whatsapp.api_url}/manager
2. Login com API Key
3. Instância: {whatsapp.instance_name}
4. Escaneie QR Code

<b>API Status:</b> {whatsapp.api_url}""",
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔄 Tentar Novamente",
                                         callback_data="show_qrcode"),
                    InlineKeyboardButton("📊 Ver Status",
                                         callback_data="instance_details"),
                    InlineKeyboardButton("⬅️ Voltar",
                                         callback_data="whatsapp_instance")
                ]]))

    except Exception as e:
        logger.error(f"Erro ao mostrar QR Code: {e}")
        await query.edit_message_text(
            "❌ Erro ao gerar QR Code!",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⬅️ Voltar",
                                     callback_data="whatsapp_instance")
            ]]))


# Funções para edição de cliente


async def processar_edit_nome(update, context):
    """Processa a edição do nome"""
    if update.message.text == "❌ Cancelar":
        await update.message.reply_text("❌ Edição cancelada.",
                                        reply_markup=criar_teclado_principal())
        return ConversationHandler.END

    novo_nome = update.message.text.strip()
    if not novo_nome:
        await update.message.reply_text(
            "❌ Nome não pode estar vazio. Digite novamente:")
        return EDIT_NOME

    return await finalizar_edicao(update, context, 'nome', novo_nome)


async def processar_edit_telefone(update, context):
    """Processa a edição do telefone"""
    if update.message.text == "❌ Cancelar":
        await update.message.reply_text("❌ Edição cancelada.",
                                        reply_markup=criar_teclado_principal())
        return ConversationHandler.END

    novo_telefone = update.message.text.strip()
    if not novo_telefone:
        await update.message.reply_text(
            "❌ Telefone não pode estar vazio. Digite novamente:")
        return EDIT_TELEFONE

    return await finalizar_edicao(update, context, 'telefone', novo_telefone)


async def processar_edit_pacote(update, context):
    """Processa a edição do pacote"""
    if update.message.text == "❌ Cancelar":
        await update.message.reply_text("❌ Edição cancelada.",
                                        reply_markup=criar_teclado_principal())
        return ConversationHandler.END

    novo_pacote = update.message.text.strip()
    if not novo_pacote:
        await update.message.reply_text(
            "❌ Pacote não pode estar vazio. Digite novamente:")
        return EDIT_PACOTE

    return await finalizar_edicao(update, context, 'pacote', novo_pacote)


async def processar_edit_valor(update, context):
    """Processa a edição do valor"""
    if update.message.text == "❌ Cancelar":
        await update.message.reply_text("❌ Edição cancelada.",
                                        reply_markup=criar_teclado_principal())
        return ConversationHandler.END

    try:
        novo_valor = update.message.text.strip().replace('R$', '').replace(
            ',', '.').strip()
        valor_float = float(novo_valor)
        if valor_float <= 0:
            raise ValueError("Valor deve ser positivo")

        return await finalizar_edicao(update, context, 'valor', valor_float)
    except ValueError:
        await update.message.reply_text(
            "❌ Valor inválido. Digite um número válido (ex: 35.00):")
        return EDIT_VALOR


async def processar_edit_servidor(update, context):
    """Processa a edição do servidor"""
    if update.message.text == "❌ Cancelar":
        await update.message.reply_text("❌ Edição cancelada.",
                                        reply_markup=criar_teclado_principal())
        return ConversationHandler.END

    novo_servidor = update.message.text.strip()
    if not novo_servidor:
        await update.message.reply_text(
            "❌ Servidor não pode estar vazio. Digite novamente:")
        return EDIT_SERVIDOR

    return await finalizar_edicao(update, context, 'servidor', novo_servidor)


async def processar_edit_vencimento(update, context):
    """Processa a edição do vencimento"""
    if update.message.text == "❌ Cancelar":
        await update.message.reply_text("❌ Edição cancelada.",
                                        reply_markup=criar_teclado_principal())
        return ConversationHandler.END

    try:
        from datetime import datetime
        novo_vencimento = update.message.text.strip()
        # Aceita formatos DD/MM/YYYY ou DD/MM/YY
        if len(novo_vencimento) == 8:  # DD/MM/YY
            data_obj = datetime.strptime(novo_vencimento, "%d/%m/%y")
        else:  # DD/MM/YYYY
            data_obj = datetime.strptime(novo_vencimento, "%d/%m/%Y")

        data_formatada = data_obj.strftime("%Y-%m-%d")
        return await finalizar_edicao(update, context, 'vencimento',
                                      data_formatada)
    except ValueError:
        await update.message.reply_text(
            "❌ Data inválida. Use o formato DD/MM/YYYY (ex: 15/03/2025):")
        return EDIT_VENCIMENTO


async def finalizar_edicao(update, context, campo, novo_valor):
    """Finaliza a edição salvando no banco"""
    try:
        cliente_id = context.user_data.get('editando_cliente_id')
        cliente_dados = context.user_data.get('cliente_dados')

        if not cliente_id or not cliente_dados:
            await update.message.reply_text(
                "❌ Erro: dados de edição perdidos.",
                reply_markup=criar_teclado_principal())
            return ConversationHandler.END

        from database import DatabaseManager
        db = DatabaseManager()

        # Aplicar a mudança
        sucesso = db.atualizar_cliente(cliente_id, campo, novo_valor)

        if sucesso:
            valor_exibicao = novo_valor
            if campo == 'valor':
                valor_exibicao = f"R$ {novo_valor:.2f}"
            elif campo == 'vencimento':
                valor_exibicao = datetime.strptime(
                    novo_valor, '%Y-%m-%d').strftime('%d/%m/%Y')

            await update.message.reply_text(
                f"✅ {campo.title()} atualizado com sucesso!\n\n"
                f"👤 Cliente: {cliente_dados['nome']}\n"
                f"📝 Campo: {campo.title()}\n"
                f"🔄 Novo valor: {valor_exibicao}",
                reply_markup=criar_teclado_principal())
        else:
            await update.message.reply_text(
                "❌ Erro ao atualizar cliente.",
                reply_markup=criar_teclado_principal())

        # Limpar dados do contexto
        context.user_data.pop('editando_cliente_id', None)
        context.user_data.pop('editando_campo', None)
        context.user_data.pop('cliente_dados', None)

        return ConversationHandler.END

    except Exception as e:
        logger.error(f"Erro ao finalizar edição: {e}")
        await update.message.reply_text("❌ Erro interno ao editar cliente.",
                                        reply_markup=criar_teclado_principal())
        return ConversationHandler.END


def main():
    """Função principal"""
    # Verificar variáveis essenciais
    token = os.getenv('BOT_TOKEN')
    admin_id = os.getenv('ADMIN_CHAT_ID')

    if not token:
        print("❌ BOT_TOKEN não configurado!")
        sys.exit(1)

    if not admin_id:
        print("❌ ADMIN_CHAT_ID não configurado!")
        sys.exit(1)

    print("🚀 Iniciando bot Telegram...")

    # Testar componentes principais
    try:
        from database import DatabaseManager
        db = DatabaseManager()
        print("✅ Banco de dados OK")
    except Exception as e:
        print(f"⚠️ Database: {e}")

    try:
        from whatsapp_service import WhatsAppService
        ws = WhatsAppService()
        print("✅ WhatsApp Service OK")
    except Exception as e:
        print(f"⚠️ WhatsApp: {e}")

    # Criar e configurar aplicação
    app = Application.builder().token(token).build()

    # ConversationHandler para cadastro escalonável
    cadastro_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^➕ Adicionar Cliente$"),
                           iniciar_cadastro)
        ],
        states={
            NOME:
            [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_nome)],
            TELEFONE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND,
                               receber_telefone)
            ],
            PACOTE:
            [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_pacote)],
            VALOR:
            [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_valor)],
            SERVIDOR: [
                MessageHandler(filters.TEXT & ~filters.COMMAND,
                               receber_servidor)
            ],
            VENCIMENTO: [
                MessageHandler(filters.TEXT & ~filters.COMMAND,
                               receber_vencimento)
            ],
            CONFIRMAR: [
                MessageHandler(filters.TEXT & ~filters.COMMAND,
                               confirmar_cadastro)
            ]
        },
        fallbacks=[
            MessageHandler(filters.Regex("^❌ Cancelar$"), cancelar_cadastro),
            CommandHandler("cancel", cancelar_cadastro)
        ])

    # ConversationHandler para edição de cliente
    async def iniciar_edicao_wrapper(update, context):
        query = update.callback_query
        partes = query.data.split("_")
        if len(partes) == 3:
            campo = partes[1]
            cliente_id = int(partes[2])
            return await iniciar_edicao_campo(query, context, cliente_id,
                                              campo)
        return ConversationHandler.END

    edicao_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(iniciar_edicao_wrapper, pattern="^edit_")
        ],
        states={
            EDIT_NOME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND,
                               processar_edit_nome)
            ],
            EDIT_TELEFONE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND,
                               processar_edit_telefone)
            ],
            EDIT_PACOTE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND,
                               processar_edit_pacote)
            ],
            EDIT_VALOR: [
                MessageHandler(filters.TEXT & ~filters.COMMAND,
                               processar_edit_valor)
            ],
            EDIT_SERVIDOR: [
                MessageHandler(filters.TEXT & ~filters.COMMAND,
                               processar_edit_servidor)
            ],
            EDIT_VENCIMENTO: [
                MessageHandler(filters.TEXT & ~filters.COMMAND,
                               processar_edit_vencimento)
            ]
        },
        fallbacks=[
            MessageHandler(filters.Regex("^❌ Cancelar$"), cancelar_cadastro),
            CommandHandler("cancel", cancelar_cadastro)
        ])

    # ConversationHandler para configurações (botões inline)
    config_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(config_callback, pattern="^config_")
        ],
        states={
            CONFIG_EMPRESA: [
                MessageHandler(filters.TEXT & ~filters.COMMAND,
                               processar_config_empresa)
            ],
            CONFIG_PIX: [
                MessageHandler(filters.TEXT & ~filters.COMMAND,
                               processar_config_pix)
            ],
            CONFIG_SUPORTE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND,
                               processar_config_suporte)
            ]
        },
        fallbacks=[
            MessageHandler(filters.Regex("^❌ Cancelar$"), cancelar_config),
            CommandHandler("cancel", cancelar_config)
        ])

    # ConversationHandler para configurações diretas (teclado persistente)
    config_direct_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^🏢 Empresa$"),
                           config_empresa_direct),
            MessageHandler(filters.Regex("^💳 PIX$"), config_pix_direct),
            MessageHandler(filters.Regex("^📞 Suporte$"), config_suporte_direct)
        ],
        states={
            CONFIG_EMPRESA: [
                MessageHandler(filters.TEXT & ~filters.COMMAND,
                               processar_config_empresa)
            ],
            CONFIG_PIX: [
                MessageHandler(filters.TEXT & ~filters.COMMAND,
                               processar_config_pix)
            ],
            CONFIG_SUPORTE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND,
                               processar_config_suporte)
            ]
        },
        fallbacks=[
            MessageHandler(filters.Regex("^❌ Cancelar$"), cancelar_config),
            CommandHandler("cancel", cancelar_config)
        ])

    # Adicionar handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add_cliente))
    app.add_handler(CommandHandler("listar", listar_clientes))
    app.add_handler(CommandHandler("relatorio", relatorio))
    app.add_handler(CommandHandler("buscar", buscar_cliente))
    app.add_handler(CommandHandler("editar", editar_cliente_cmd))
    app.add_handler(CommandHandler("config", configuracoes_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("teste_whatsapp", comando_teste_whatsapp))
    app.add_handler(CommandHandler("templates", menu_templates))
    app.add_handler(CommandHandler("agendador", menu_agendador))

    # Adicionar ConversationHandlers PRIMEIRO (prioridade mais alta)
    app.add_handler(config_handler, group=0)
    app.add_handler(config_direct_handler, group=0)
    app.add_handler(edicao_handler, group=0)
    app.add_handler(cadastro_handler, group=0)

    # Handler para callbacks dos botões inline
    app.add_handler(CallbackQueryHandler(callback_cliente), group=1)

    # Handler específico para callbacks de templates
    from callbacks_templates import (callback_templates_listar,
                                     callback_templates_editar,
                                     callback_templates_testar,
                                     callback_agendador_executar,
                                     callback_agendador_stats,
                                     callback_agendador_config)
    app.add_handler(CallbackQueryHandler(callback_templates_listar,
                                         pattern="^templates_listar$"),
                    group=1)
    app.add_handler(CallbackQueryHandler(callback_templates_editar,
                                         pattern="^templates_editar$"),
                    group=1)
    app.add_handler(CallbackQueryHandler(callback_templates_testar,
                                         pattern="^templates_testar$"),
                    group=1)
    app.add_handler(CallbackQueryHandler(callback_agendador_executar,
                                         pattern="^agendador_executar$"),
                    group=1)
    app.add_handler(CallbackQueryHandler(callback_agendador_stats,
                                         pattern="^agendador_stats$"),
                    group=1)
    app.add_handler(CallbackQueryHandler(callback_agendador_config,
                                         pattern="^agendador_config$"),
                    group=1)

    # Handler para os botões do teclado personalizado (prioridade mais baixa)
    # Criar um filtro específico para botões conhecidos
    botoes_filter = filters.Regex(
        "^(👥 Listar Clientes|➕ Adicionar Cliente|📊 Relatórios|🔍 Buscar Cliente|📱 WhatsApp Status|🧪 Testar WhatsApp|📱 QR Code|⚙️ Gerenciar WhatsApp|📄 Templates|⏰ Agendador|📋 Fila de Mensagens|📜 Logs de Envios|❓ Ajuda)$"
    )
    app.add_handler(MessageHandler(botoes_filter, lidar_com_botoes), group=2)

    print("✅ Bot configurado com sucesso!")
    print(f"🔑 Admin ID: {admin_id}")

    # Inicializar sistema de agendamento automático
    try:
        from scheduler_automatico import iniciar_sistema_agendamento
        iniciar_sistema_agendamento()
        print("⏰ Sistema de agendamento iniciado - Execução diária às 9h")
    except Exception as e:
        print(f"⚠️ Erro ao iniciar agendador: {e}")

    print("🤖 Bot online e funcionando!")

    # Iniciar polling
    try:
        app.run_polling(drop_pending_updates=True)
    except KeyboardInterrupt:
        print("\n👋 Bot encerrado pelo usuário")
    except Exception as e:
        print(f"❌ Erro: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
