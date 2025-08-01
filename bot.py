import os
from datetime import datetime, timedelta
import logging
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
)
from dotenv import load_dotenv
from database import DatabaseManager  # Implemente essa classe em outro arquivo

load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ALLOWED_USERS = set(map(int, os.getenv("ALLOWED_USERS", "").split(",")))

logging.basicConfig(level=logging.INFO)

# ================== WHATSAPP ==================
import aiohttp
async def enviar_whatsapp(telefone, mensagem):
    url = os.getenv("EVOLUTION_API_URL")
    token = os.getenv("EVOLUTION_API_TOKEN")
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json={"number": telefone, "message": mensagem}) as resp:
            return resp.status == 200

# ================== LISTAR CLIENTES ==================
async def listar_clientes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ALLOWED_USERS:
        await update.message.reply_text("❌ Acesso negado.")
        return

    db = DatabaseManager()
    clientes = db.listar_clientes()

    if not clientes:
        await update.message.reply_text("📋 Nenhum cliente cadastrado ainda.")
        return

    clientes_ordenados = []
    for c in clientes:
        try:
            c['vencimento_obj'] = datetime.strptime(c['vencimento'], '%Y-%m-%d')
            c['dias_restantes'] = (c['vencimento_obj'] - datetime.now()).days
            clientes_ordenados.append(c)
        except Exception:
            continue

    clientes_ordenados.sort(key=lambda x: x['vencimento_obj'])

    keyboard = []
    for cliente in clientes_ordenados:
        nome = cliente['nome']
        venc = cliente['vencimento_obj'].strftime('%d/%m')
        status = "🟢"
        if cliente['dias_restantes'] < 0:
            status = "🔴"
        elif cliente['dias_restantes'] == 0:
            status = "⚠️"
        elif cliente['dias_restantes'] <= 3:
            status = "🟡"

        btn = InlineKeyboardButton(
            f"{status} {nome} - R$ {cliente['valor']:.0f} - {venc}",
            callback_data=f"cliente_{cliente['id']}"
        )
        keyboard.append([btn])

    await update.message.reply_text(
        "👥 *Clientes (ordenados por vencimento)*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ================== CALLBACK INLINE ==================
async def callback_inline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    db = DatabaseManager()

    if data.startswith("cliente_"):
        cliente_id = int(data.split("_")[1])
        cliente = db.buscar_cliente_por_id(cliente_id)
        if not cliente:
            await query.edit_message_text("❌ Cliente não encontrado.")
            return

        vencimento_br = datetime.strptime(cliente['vencimento'], "%Y-%m-%d").strftime("%d/%m/%Y")
        msg = (
            f"👤 *{cliente['nome']}*\n"
            f"📱 {cliente['telefone']}\n"
            f"📦 {cliente['pacote']}\n"
            f"💰 R$ {cliente['valor']:.2f}\n"
            f"📅 Vencimento: {vencimento_br}"
        )

        keyboard = [
            [
                InlineKeyboardButton("📧 Enviar lembrete", callback_data=f"lembrete_{cliente_id}"),
                InlineKeyboardButton("🔄 Renovar", callback_data=f"renovar_{cliente_id}")
            ],
            [
                InlineKeyboardButton("📦 Alterar pacote", callback_data=f"alterar_pacote_{cliente_id}"),
                InlineKeyboardButton("📅 Alterar vencimento", callback_data=f"alterar_venc_{cliente_id}")
            ],
            [
                InlineKeyboardButton("✏️ Editar", callback_data=f"editar_{cliente_id}"),
                InlineKeyboardButton("🗑️ Excluir", callback_data=f"confirmar_excluir_{cliente_id}")
            ],
            [
                InlineKeyboardButton("⬅️ Voltar", callback_data="voltar_lista")
            ]
        ]
        await query.edit_message_text(
            text=msg, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data.startswith("lembrete_"):
        cliente_id = int(data.split("_")[1])
        cliente = db.buscar_cliente_por_id(cliente_id)
        vencimento = datetime.strptime(cliente['vencimento'], "%Y-%m-%d").strftime('%d/%m/%Y')
        mensagem = f"🔔 Olá {cliente['nome']}, lembramos que seu plano '{cliente['pacote']}' vence em {vencimento}. Valor: R$ {cliente['valor']:.2f}"
        sucesso = await enviar_whatsapp(cliente['telefone'], mensagem)
        texto = "✅ Mensagem enviada!" if sucesso else "❌ Falha ao enviar mensagem."
        await query.edit_message_text(texto)

    elif data.startswith("renovar_"):
        cliente_id = int(data.split("_")[1])
        cliente = db.buscar_cliente_por_id(cliente_id)
        dias = {
            "1 mês": 30,
            "3 meses": 90,
            "6 meses": 180,
            "12 meses": 365
        }.get(cliente["pacote"], 30)
        vencimento = datetime.strptime(cliente['vencimento'], "%Y-%m-%d")
        novo_venc = vencimento + timedelta(days=dias)
        db.atualizar_cliente(cliente_id, "vencimento", novo_venc.strftime('%Y-%m-%d'))
        await query.edit_message_text(f"✅ Renovado até {novo_venc.strftime('%d/%m/%Y')}!")

    elif data.startswith("confirmar_excluir_"):
        cliente_id = int(data.split("_")[2])
        keyboard = [
            [
                InlineKeyboardButton("✅ Confirmar", callback_data=f"excluir_{cliente_id}"),
                InlineKeyboardButton("❌ Cancelar", callback_data="voltar_lista")
            ]
        ]
        await query.edit_message_text("⚠️ Tem certeza que deseja excluir o cliente?", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("excluir_"):
        cliente_id = int(data.split("_")[1])
        sucesso = db.excluir_cliente(cliente_id)
        texto = "✅ Cliente excluído." if sucesso else "❌ Erro ao excluir."
        await query.edit_message_text(texto)

    elif data == "voltar_lista":
        await listar_clientes(update, context)

# ================== MAIN ==================
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", listar_clientes))
    app.add_handler(CommandHandler("listar", listar_clientes))
    app.add_handler(CallbackQueryHandler(callback_inline))

    app.run_polling()

if __name__ == "__main__":
    main()
