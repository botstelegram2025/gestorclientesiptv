import os
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes,
    ConversationHandler, MessageHandler, filters
)

# Estados para conversas
ADD_NAME, ADD_PHONE, SEND_CLIENTE, SEND_MSG = range(4)

clientes = {}

# Mensagens padrão
mensagens_padrao = {
    "promo": "Olá {nome}, confira nossa promoção especial!",
    "lembrete": "Olá {nome}, só passando para lembrar do seu compromisso amanhã.",
}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Bem-vindo ao Bot de Gestão de Clientes!\n"
        "Comandos:\n"
        "/addcliente - adicionar cliente\n"
        "/listclientes - listar clientes\n"
        "/enviamsg - enviar mensagem padrão"
    )

async def add_cliente(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Digite o nome do cliente:")
    return ADD_NAME

async def add_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['nome'] = update.message.text
    await update.message.reply_text("Agora digite o telefone do cliente (com DDD):")
    return ADD_PHONE

async def add_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telefone = update.message.text
    nome = context.user_data['nome']
    clientes[telefone] = nome
    await update.message.reply_text(f"Cliente {nome} com telefone {telefone} adicionado!")
    return ConversationHandler.END

async def list_clientes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not clientes:
        await update.message.reply_text("Nenhum cliente cadastrado.")
        return
    msg = "Clientes cadastrados:\n"
    for tel, nome in clientes.items():
        msg += f"- {nome}: {tel}\n"
    await update.message.reply_text(msg)

async def enviar_msg_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not clientes:
        await update.message.reply_text("Nenhum cliente cadastrado para enviar mensagem.")
        return ConversationHandler.END
    await update.message.reply_text("Digite o telefone do cliente para quem deseja enviar mensagem:")
    return SEND_CLIENTE

async def enviar_msg_cliente(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telefone = update.message.text
    if telefone not in clientes:
        await update.message.reply_text("Cliente não encontrado. Tente novamente ou use /cancel para sair.")
        return SEND_CLIENTE
    context.user_data['telefone'] = telefone
    await update.message.reply_text("Digite o tipo de mensagem (promo ou lembrete):")
    return SEND_MSG

async def enviar_msg_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tipo = update.message.text.lower()
    telefone = context.user_data['telefone']
    nome = clientes[telefone]

    if tipo not in mensagens_padrao:
        await update.message.reply_text("Tipo inválido. Use 'promo' ou 'lembrete'. Tente novamente ou /cancel.")
        return SEND_MSG

    # Simulação do envio WhatsApp (aqui você integraria com API real)
    texto = mensagens_padrao[tipo].format(nome=nome)
    await update.message.reply_text(f"Mensagem para {nome} ({telefone}) enviada via WhatsApp:\n\n{texto}")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Operação cancelada.")
    return ConversationHandler.END

def main():
    token = os.getenv("BOT_TOKEN")
    if not token:
        print("❌ ERRO: Variável de ambiente BOT_TOKEN não definida!")
        return

    application = ApplicationBuilder().token(token).build()

    conv_add_cliente = ConversationHandler(
        entry_points=[CommandHandler('addcliente', add_cliente)],
        states={
            ADD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_name)],
            ADD_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_phone)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    conv_enviar_msg = ConversationHandler(
        entry_points=[CommandHandler('enviamsg', enviar_msg_start)],
        states={
            SEND_CLIENTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, enviar_msg_cliente)],
            SEND_MSG: [MessageHandler(filters.TEXT & ~filters.COMMAND, enviar_msg_text)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    application.add_handler(CommandHandler('start', start))
    application.add_handler(conv_add_cliente)
    application.add_handler(CommandHandler('listclientes', list_clientes))
    application.add_handler(conv_enviar_msg)
    application.add_handler(CommandHandler('cancel', cancel))

    application.run_polling()

if __name__ == '__main__':
    main()
