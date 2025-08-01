"""
Callbacks para o sistema de templates e agendador
Funções de callback que serão integradas ao bot principal
"""

import logging
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime

logger = logging.getLogger(__name__)

async def callback_templates_listar(query, context):
    """Callback para listar templates detalhadamente"""
    try:
        from templates_system import TemplateManager
        
        template_manager = TemplateManager()
        templates = template_manager.listar_templates()
        
        if not templates:
            await query.edit_message_text(
                "📄 Nenhum template encontrado.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("⬅️ Voltar", callback_data="menu_principal")
                ]])
            )
            return
        
        mensagem = "📄 <b>TEMPLATES DETALHADOS</b>\n"
        
        for template in templates:
            status = "✅ Ativo" if template.ativo else "❌ Inativo"
            mensagem += f"\n<b>{template.titulo}</b>"
            mensagem += f"\n📝 Tipo: {template.tipo.replace('_', ' ').title()}"
            mensagem += f"\n🔘 Status: {status}"
            mensagem += f"\n📄 Prévia: {template.conteudo[:50]}..."
            mensagem += "\n" + "─" * 30
        
        keyboard = [
            [InlineKeyboardButton("⬅️ Voltar", callback_data="menu_principal")]
        ]
        
        await query.edit_message_text(
            mensagem,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    except Exception as e:
        logger.error(f"Erro ao listar templates: {e}")
        await query.edit_message_text(
            "❌ Erro ao carregar templates",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⬅️ Voltar", callback_data="menu_principal")
            ]])
        )

async def callback_templates_editar(query, context):
    """Callback para editar templates"""
    mensagem = """✏️ <b>EDITAR TEMPLATES</b>

Os templates são definidos no código para manter consistência.
Para personalizar as mensagens, você pode:

1. <b>Configurar dados da empresa:</b>
   • 🏢 Empresa (nome da empresa)
   • 💳 PIX (chave PIX)
   • 📞 Suporte (contato)

2. <b>Tipos de template disponíveis:</b>
   • <b>3 dias antes:</b> Lembrete amigável
   • <b>1 dia antes:</b> Aviso urgente
   • <b>1 dia atrasado:</b> Cobrança

<i>Os templates se adaptam automaticamente aos dados de cada cliente.</i>"""
    
    keyboard = [
        [InlineKeyboardButton("🏢 Config. Empresa", callback_data="config_empresa")],
        [InlineKeyboardButton("💳 Config. PIX", callback_data="config_pix")],
        [InlineKeyboardButton("📞 Config. Suporte", callback_data="config_suporte")],
        [InlineKeyboardButton("⬅️ Voltar", callback_data="menu_principal")]
    ]
    
    await query.edit_message_text(
        mensagem,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def callback_templates_testar(query, context):
    """Callback para testar template com dados reais"""
    try:
        from templates_system import TemplateManager
        from database import DatabaseManager
        
        # Buscar um cliente para teste
        db = DatabaseManager()
        clientes = db.listar_clientes()
        
        if not clientes:
            await query.edit_message_text(
                "❌ Nenhum cliente cadastrado para teste de template.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("⬅️ Voltar", callback_data="menu_principal")
                ]])
            )
            return
        
        template_manager = TemplateManager()
        template = template_manager.buscar_template_por_nome('vencimento_3_dias')
        
        if not template:
            await query.edit_message_text(
                "❌ Template de teste não encontrado.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("⬅️ Voltar", callback_data="menu_principal")
                ]])
            )
            return
        
        # Usar primeiro cliente para teste
        cliente = clientes[0]
        dados_cliente = {
            'nome': cliente.get('nome', 'Cliente Teste'),
            'telefone': cliente.get('telefone', ''),
            'valor': cliente.get('valor', '50.00'),
            'data_vencimento': '15/02/2025'
        }
        
        mensagem_formatada = template_manager.formatar_mensagem(template, dados_cliente)
        
        resultado = f"""🧪 <b>TESTE DE TEMPLATE</b>

<b>Template:</b> {template.titulo}
<b>Cliente de teste:</b> {dados_cliente['nome']}

<b>Mensagem que seria enviada:</b>
──────────────────────
{mensagem_formatada}
──────────────────────

<i>Esta é apenas uma prévia. Para envio real, use o sistema de agendamento.</i>"""
        
        keyboard = [
            [InlineKeyboardButton("🔄 Testar Outro", callback_data="templates_testar")],
            [InlineKeyboardButton("⬅️ Voltar", callback_data="menu_principal")]
        ]
        
        await query.edit_message_text(
            resultado,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    except Exception as e:
        logger.error(f"Erro ao testar template: {e}")
        await query.edit_message_text(
            f"❌ Erro ao testar template: {str(e)[:100]}",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⬅️ Voltar", callback_data="menu_principal")
            ]])
        )

async def callback_agendador_executar(query, context):
    """Callback para executar agendador agora"""
    try:
        from scheduler_automatico import AgendadorAutomatico
        
        await query.edit_message_text("⏰ Executando verificação de vencimentos...")
        
        agendador = AgendadorAutomatico()
        resultado = agendador.executar_agora_teste()
        
        if resultado['sucesso']:
            stats = resultado['resultado']
            mensagem = f"""✅ <b>EXECUÇÃO CONCLUÍDA</b>

📊 <b>Resultados:</b>
• 📅 3 dias antes: {stats['vencimento_3_dias']} enviados
• ⚠️ 1 dia antes: {stats['vencimento_1_dia']} enviados  
• 🔴 1 dia atrasado: {stats['vencido_1_dia']} enviados

📈 <b>Total:</b> {stats['total_enviados']} sucessos / {stats['total_falhas']} falhas

⏰ <b>Executado em:</b> {resultado['executado_em']}"""
        else:
            mensagem = f"""❌ <b>ERRO NA EXECUÇÃO</b>

🔍 <b>Problema:</b> {resultado.get('erro', 'Erro desconhecido')}

⏰ <b>Tentativa em:</b> {resultado['executado_em']}

Verifique:
• WhatsApp conectado
• Templates configurados  
• Clientes cadastrados"""
        
        keyboard = [
            [InlineKeyboardButton("🔄 Executar Novamente", callback_data="agendador_executar")],
            [InlineKeyboardButton("📊 Ver Estatísticas", callback_data="agendador_stats")],
            [InlineKeyboardButton("⬅️ Voltar", callback_data="menu_principal")]
        ]
        
        await query.edit_message_text(
            mensagem,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    except Exception as e:
        logger.error(f"Erro ao executar agendador: {e}")
        await query.edit_message_text(
            f"❌ Erro ao executar agendador: {str(e)[:100]}",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⬅️ Voltar", callback_data="menu_principal")
            ]])
        )

async def callback_agendador_stats(query, context):
    """Callback para mostrar estatísticas do agendador"""
    try:
        from scheduler_automatico import AgendadorAutomatico
        
        agendador = AgendadorAutomatico()
        
        # Obter status do sistema
        status = agendador.obter_status_agendador()
        
        # Estatísticas simplificadas
        historico_7d = {
            'total_enviados': 0,
            'sucessos': 0, 
            'falhas': 0,
            'taxa_sucesso': 0.0
        }
        historico_30d = {
            'total_enviados': 0,
            'sucessos': 0,
            'falhas': 0, 
            'taxa_sucesso': 0.0
        }
        
        status_icon = "🟢" if status['rodando'] else "🔴"
        
        mensagem = f"""📊 <b>ESTATÍSTICAS DO AGENDADOR</b>

{status_icon} <b>Status:</b> {"Ativo" if status['rodando'] else "Inativo"}
⏰ <b>Próxima execução:</b> {status['proxima_execucao']}
🔧 <b>Jobs ativos:</b> {status['jobs_ativos']}

📈 <b>Últimos 7 dias:</b>
• Total enviado: {historico_7d['total_enviados']}
• Sucessos: {historico_7d['sucessos']}
• Falhas: {historico_7d['falhas']}
• Taxa sucesso: {historico_7d['taxa_sucesso']:.1f}%

📊 <b>Últimos 30 dias:</b>
• Total enviado: {historico_30d['total_enviados']}
• Sucessos: {historico_30d['sucessos']}
• Falhas: {historico_30d['falhas']}
• Taxa sucesso: {historico_30d['taxa_sucesso']:.1f}%

<i>Atualizado em: {datetime.now().strftime('%d/%m/%Y às %H:%M:%S')}</i>"""
        
        keyboard = [
            [InlineKeyboardButton("🚀 Executar Agora", callback_data="agendador_executar")],
            [InlineKeyboardButton("🔄 Atualizar Stats", callback_data="agendador_stats")],
            [InlineKeyboardButton("⬅️ Voltar", callback_data="menu_principal")]
        ]
        
        await query.edit_message_text(
            mensagem,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    except Exception as e:
        logger.error(f"Erro ao obter estatísticas: {e}")
        await query.edit_message_text(
            f"❌ Erro ao carregar estatísticas: {str(e)[:100]}",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⬅️ Voltar", callback_data="menu_principal")
            ]])
        )

async def callback_agendador_config(query, context):
    """Callback para configurações do agendador"""
    try:
        from scheduler_automatico import AgendadorAutomatico
        
        agendador = AgendadorAutomatico()
        status = agendador.obter_status_agendador()
        
        status_icon = "🟢" if status['rodando'] else "🔴"
        
        mensagem = f"""⚙️ <b>CONFIGURAÇÕES DO AGENDADOR</b>

{status_icon} <b>Status atual:</b> {"Ativo" if status['rodando'] else "Inativo"}
⏰ <b>Horário de execução:</b> {status['horario_execucao']}
🔧 <b>Jobs configurados:</b> {status['jobs_ativos']}

<b>🎯 Tipos de notificação:</b>
• <b>3 dias antes:</b> Lembrete amigável
• <b>1 dia antes:</b> Aviso urgente
• <b>1 dia atrasado:</b> Cobrança

<b>⚙️ Configuração atual:</b>
• Execução diária às 9h da manhã
• Fuso horário: América/São_Paulo
• Rate limiting: 20 msgs/min
• Retry automático em caso de falha

<i>O agendador roda automaticamente todos os dias e verifica clientes com vencimentos nas datas configuradas.</i>"""
        
        keyboard = [
            [InlineKeyboardButton("🚀 Executar Teste", callback_data="agendador_executar")],
            [InlineKeyboardButton("📊 Ver Estatísticas", callback_data="agendador_stats")],
            [InlineKeyboardButton("⬅️ Voltar", callback_data="menu_principal")]
        ]
        
        await query.edit_message_text(
            mensagem,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    except Exception as e:
        logger.error(f"Erro ao mostrar configurações: {e}")
        await query.edit_message_text(
            f"❌ Erro ao carregar configurações: {str(e)[:100]}",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⬅️ Voltar", callback_data="menu_principal")
            ]])
        )