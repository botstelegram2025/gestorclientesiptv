import logging
import asyncio
from telegram import Update
from telegram.ext import (ApplicationBuilder, CommandHandler, CallbackQueryHandler,
                          ConversationHandler, ContextTypes)

from config import TOKEN, ADMIN_CHAT_ID, MENSAGENS
from database import criar_tabela
from whatsapp_service import WhatsAppService
from callbacks_templates import (
    callback_templates_listar,
    callback_templates_editar,
    callback_templates_testar,
    callback_agendador_executar,
    callback_agendador_stats
)

# Configuração de logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Comando /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = update.effective_chat.id

    if chat_id != ADMIN_CHAT_ID:
        await update.message.reply_text(MENSAGENS["acesso_negado"])
        return

    await update.message.reply_text(MENSAGENS["bem_vindo"], parse_mode='Markdown')

# Menu principal com callbacks
async def callback_menu_principal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.edit_message_text(
        text=MENSAGENS["bem_vindo"], parse_mode='Markdown'
    )

# Função principal
async def main():
    if not TOKEN:
        logger.error("Token do bot não encontrado. Verifique a variável BOT_TOKEN no ambiente.")
        return

    criar_tabela()  # Garante que o banco esteja pronto

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_menu_principal, pattern="menu_principal"))
    app.add_handler(CallbackQueryHandler(callback_templates_listar, pattern="templates_listar"))
    app.add_handler(CallbackQueryHandler(callback_templates_editar, pattern="templates_editar"))
    app.add_handler(CallbackQueryHandler(callback_templates_testar, pattern="templates_testar"))
    app.add_handler(CallbackQueryHandler(callback_agendador_executar, pattern="agendador_executar"))
    app.add_handler(CallbackQueryHandler(callback_agendador_stats, pattern="agendador_stats"))

    logger.info("Bot iniciado com sucesso!")
    await app.run_polling()
  
if __name__ == '__main__':
    import nest_asyncio
    nest_asyncio.apply()

    asyncio.get_event_loop().run_until_complete(main())

