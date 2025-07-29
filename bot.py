# Estrutura principal do bot
# Arquivo: main.py

import os
import asyncio
from datetime import time
from dotenv import load_dotenv
from telegram.ext import (ApplicationBuilder, CommandHandler, MessageHandler,
                          filters, ConversationHandler, CallbackQueryHandler)

from handlers.cadastro import cadastro_handler
from handlers.mensagens import mensagens_handler
from handlers.relatorio import (
    list_clientes, renovar_cliente, exportar, relatorio, callback_opcoes
)
from handlers.cancelar import cancelar
from jobs.alerta_admin import lembrar_admin_vencimentos
from utils.teclado import teclado_principal

# Carrega variáveis de ambiente
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "0"))

def main():
    from database.db import criar_tabelas
    criar_tabelas()

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(cadastro_handler)
    app.add_handler(mensagens_handler)
    app.add_handler(MessageHandler(filters.Regex("^(📋 Listar Clientes)$"), list_clientes))
    app.add_handler(MessageHandler(filters.Regex("^(🔄 Renovar Plano)$"), renovar_cliente))
    app.add_handler(MessageHandler(filters.Regex("^(📤 Exportar Dados)$"), exportar))
    app.add_handler(MessageHandler(filters.Regex("^(📊 Relatório)$"), relatorio))
    app.add_handler(MessageHandler(filters.Regex("^(❌ Cancelar Operação)$"), cancelar))
    app.add_handler(CallbackQueryHandler(callback_opcoes))

    # Agenda diário às 09:00h
    app.job_queue.run_daily(lambda ctx: lembrar_admin_vencimentos(ctx, ADMIN_CHAT_ID), time(hour=9, minute=0))

    app.run_polling()

async def start(update, context):
    await update.message.reply_text(
        "👋 Bem-vindo ao Bot de Gestão de Clientes!\n\nEscolha uma opção:",
        reply_markup=teclado_principal()
    )

if __name__ == "__main__":
    asyncio.run(main())
