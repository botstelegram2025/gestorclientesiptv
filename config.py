"""
Configurações do sistema
"""

import os

# Token do bot Telegram
TOKEN = os.getenv("BOT_TOKEN")

# ID do chat do administrador
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "0"))

# Configurações da Evolution API
EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL", "http://localhost:8080")
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "")
EVOLUTION_INSTANCE_NAME = os.getenv("EVOLUTION_INSTANCE_NAME", "default")

# Configurações do banco de dados
DB_PATH = "clientes.db"

# Estados da conversa
ADD_NAME, ADD_PHONE, ADD_PACOTE, ADD_PLANO, ADD_SERVIDOR, ALTERAR_VENCIMENTO = range(6)
CONFIG_PIX, CONFIG_EMPRESA, CONFIG_CONTATO = range(6, 9)
ENVIO_MANUAL_TELEFONE, ENVIO_MANUAL_MENSAGEM = range(9, 11)
EDIT_CLIENTE_FIELD, EDIT_CLIENTE_VALUE = range(11, 13)

# Opções de pacotes
PACOTES = ["1 mês", "3 meses", "6 meses", "1 ano"]

# Opções de planos (valores em R$)
PLANOS = [30, 35, 40, 45, 60, 65, 70, 90, 110, 135]

# Servidores disponíveis
SERVIDORES = [
    ("fast play", "⚡"),
    ("genial tv", "🎯"),
    ("eitv", "📺"),
    ("gold play", "🏆"),
    ("slim tv", "🎬"),
    ("unitv", "🧩"),
    ("live21", "🌐"),
    ("ztech play", "🔧"),
    ("xserver play", "🚀")
]

# Mensagens do sistema
MENSAGENS = {
    "bem_vindo": """
🤖 *Sistema de Gestão de Clientes*

Olá! Eu sou seu assistente para gerenciar clientes e notificações de vencimento.

*Funcionalidades disponíveis:*
• ➕ Adicionar novos clientes
• 📋 Listar todos os clientes
• ⏰ Filtrar por vencimentos
• 📊 Gerar relatórios
• 📤 Exportar dados
• ⚙️ Configurações do sistema
• 📲 Envio manual via WhatsApp

Use o menu abaixo para navegar:
    """,
    
    "ajuda": """
🆘 *Ajuda do Sistema*

*Comandos disponíveis:*
• `/start` - Iniciar o bot
• `/menu` - Mostrar menu principal
• `/help` - Mostrar esta ajuda
• `/cancel` - Cancelar operação atual

*Como usar:*
1. Use os botões do menu para navegar
2. Siga as instruções em cada etapa
3. Use "❌ Cancelar Operação" para sair

*Suporte:* Entre em contato com o administrador
    """,
    
    "operacao_cancelada": "❌ Operação cancelada. Voltando ao menu principal.",
    "erro_geral": "❌ Ocorreu um erro. Tente novamente.",
    "acesso_negado": "❌ Acesso negado. Apenas administradores podem usar este bot."
}
