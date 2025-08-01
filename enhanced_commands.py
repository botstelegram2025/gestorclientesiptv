"""
Comandos aprimorados para o sistema de notificações
Integração com o NotificationServiceImproved
"""

import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from datetime import datetime

logger = logging.getLogger(__name__)

class EnhancedCommands:
    """Comandos aprimorados com recursos avançados de notificação"""
    
    def __init__(self, notification_service, db_manager):
        self.notification_service = notification_service
        self.db = db_manager
    
    async def comando_sistema_status(self, update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /sistema_status - Status completo do sistema"""
        try:
            # Obter status completo
            status = await self.notification_service.teste_conectividade_completo()
            
            # Preparar mensagem
            msg = "🔧 **SISTEMA DE NOTIFICAÇÕES - STATUS COMPLETO**\n\n"
            
            if status['status_geral']:
                msg += "✅ **Status Geral:** OPERACIONAL\n\n"
            else:
                msg += "❌ **Status Geral:** PROBLEMAS DETECTADOS\n\n"
            
            # Status dos componentes
            msg += "📊 **Componentes:**\n"
            for componente, info in status['componentes'].items():
                icon = "✅" if info['status'] else "❌"
                nome = componente.replace('_', ' ').title()
                msg += f"{icon} **{nome}:** {info['detalhes']}\n"
            
            # Métricas
            msg += f"\n📈 **Métricas da Sessão:**\n"
            metricas = status['metricas']
            msg += f"• Enviadas: {metricas['total_enviadas']}\n"
            msg += f"• Falharam: {metricas['total_falharam']}\n"
            msg += f"• Última atualização: {metricas['ultima_atualizacao'].strftime('%H:%M:%S')}\n"
            
            # Rate limit
            rate_info = status['rate_limit']
            msg += f"\n⏱️ **Rate Limit:**\n"
            msg += f"• Status: {'🟢 OK' if rate_info['status'] else '🔴 Limitado'}\n"
            msg += f"• Mensagens no minuto: {rate_info['mensagens_no_minuto']}\n"
            
            # Botões de ação
            keyboard = [
                [InlineKeyboardButton("🔄 Atualizar", callback_data="sistema_status")],
                [InlineKeyboardButton("📊 Estatísticas", callback_data="stats_completas")],
                [InlineKeyboardButton("🧪 Teste Conectividade", callback_data="teste_conectividade")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(msg, parse_mode='Markdown', reply_markup=reply_markup)
            
        except Exception as e:
            logger.error(f"Erro no comando sistema_status: {e}")
            await update.message.reply_text(f"❌ Erro ao obter status do sistema: {e}")
    
    async def comando_notificar_lote(self, update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /notificar_lote - Envio em lote inteligente"""
        try:
            if not context.args:
                msg = ("🔄 **NOTIFICAÇÃO EM LOTE**\n\n"
                      "Uso: `/notificar_lote [tipo]`\n\n"
                      "Tipos disponíveis:\n"
                      "• `vencimento_2_dias` - Vencimentos em 2 dias\n"
                      "• `vencimento_1_dia` - Vencimentos amanhã\n"
                      "• `vencimento_hoje` - Vencimentos hoje\n"
                      "• `vencidos` - Clientes vencidos\n"
                      "• `todos_ativos` - Todos os clientes ativos\n\n"
                      "Exemplo: `/notificar_lote vencimento_hoje`")
                
                await update.message.reply_text(msg, parse_mode='Markdown')
                return
            
            tipo = context.args[0].lower()
            
            # Obter clientes baseado no tipo
            if tipo == "vencimento_2_dias":
                clientes = self.db.clientes_vencendo(2)
                template = "2_dias"
            elif tipo == "vencimento_1_dia":
                clientes = self.db.clientes_vencendo(1)
                template = "1_dia"
            elif tipo == "vencimento_hoje":
                clientes = self.db.clientes_vencendo(0)
                template = "hoje"
            elif tipo == "vencidos":
                clientes = self.db.clientes_vencidos()
                template = "vencido"
            elif tipo == "todos_ativos":
                clientes = self.db.listar_clientes_ativos()
                template = "geral"
            else:
                await update.message.reply_text("❌ Tipo inválido. Use `/notificar_lote` para ver os tipos disponíveis.")
                return
            
            if not clientes:
                await update.message.reply_text(f"ℹ️ Nenhum cliente encontrado para o tipo: {tipo}")
                return
            
            # Confirmar envio
            msg = (f"📤 **CONFIRMAR ENVIO EM LOTE**\n\n"
                  f"Tipo: {tipo.replace('_', ' ').title()}\n"
                  f"Clientes: {len(clientes)}\n"
                  f"Template: {template}\n\n"
                  f"⚠️ Esta ação enviará mensagens para {len(clientes)} clientes.\n"
                  f"Tem certeza que deseja continuar?")
            
            keyboard = [
                [InlineKeyboardButton("✅ Confirmar Envio", callback_data=f"lote_confirmar_{tipo}")],
                [InlineKeyboardButton("❌ Cancelar", callback_data="lote_cancelar")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(msg, parse_mode='Markdown', reply_markup=reply_markup)
            
        except Exception as e:
            logger.error(f"Erro no comando notificar_lote: {e}")
            await update.message.reply_text(f"❌ Erro: {e}")
    
    async def processar_lote_callback(self, update, context: ContextTypes.DEFAULT_TYPE):
        """Processa callbacks do envio em lote"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        
        if data.startswith("lote_confirmar_"):
            tipo = data.replace("lote_confirmar_", "")
            
            # Mostrar progresso
            await query.edit_message_text(
                "🚀 **PROCESSANDO ENVIO EM LOTE**\n\n"
                "⏳ Iniciando envio de notificações...\n"
                "📊 Progresso será atualizado em tempo real.",
                parse_mode='Markdown'
            )
            
            # Executar envio
            try:
                resultados = await self.notification_service.processar_vencimentos_automatico()
                
                # Criar relatório
                msg = "📋 **RELATÓRIO DE ENVIO EM LOTE**\n\n"
                msg += f"✅ **Processamento concluído!**\n\n"
                
                for categoria, quantidade in resultados.items():
                    if categoria != 'total_processados' and categoria != 'sucessos' and categoria != 'falhas':
                        msg += f"• {categoria.replace('_', ' ').title()}: {quantidade}\n"
                
                msg += f"\n📊 **Resumo:**\n"
                msg += f"• Total processados: {resultados.get('total_processados', 0)}\n"
                msg += f"• Sucessos: {resultados.get('sucessos', 0)}\n"
                msg += f"• Falhas: {resultados.get('falhas', 0)}\n"
                
                # Taxa de sucesso
                if resultados.get('total_processados', 0) > 0:
                    taxa = (resultados.get('sucessos', 0) / resultados.get('total_processados', 1)) * 100
                    msg += f"• Taxa de sucesso: {taxa:.1f}%\n"
                
                msg += f"\n🕒 Processado em: {datetime.now().strftime('%H:%M:%S')}"
                
                keyboard = [
                    [InlineKeyboardButton("📊 Ver Estatísticas", callback_data="stats_completas")],
                    [InlineKeyboardButton("🔄 Status Sistema", callback_data="sistema_status")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(msg, parse_mode='Markdown', reply_markup=reply_markup)
                
            except Exception as e:
                await query.edit_message_text(
                    f"❌ **ERRO NO ENVIO EM LOTE**\n\n"
                    f"Detalhes: {e}\n\n"
                    f"Por favor, verifique o status do sistema.",
                    parse_mode='Markdown'
                )
        
        elif data == "lote_cancelar":
            await query.edit_message_text("❌ Envio em lote cancelado.")
    
    async def comando_stats_avancado(self, update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /stats_avancado - Estatísticas detalhadas"""
        try:
            stats = self.notification_service.obter_estatisticas_detalhadas()
            
            msg = "📊 **ESTATÍSTICAS DETALHADAS**\n\n"
            
            # Estatísticas da sessão atual
            sessao = stats['sessao_atual']
            msg += "🔄 **Sessão Atual:**\n"
            msg += f"• Enviadas: {sessao['enviadas']}\n"
            msg += f"• Falharam: {sessao['falharam']}\n"
            
            if 'taxa_sucesso' in sessao:
                msg += f"• Taxa de sucesso: {sessao['taxa_sucesso']}\n"
            
            msg += f"• Última atualização: {sessao['ultima_atualizacao']}\n"
            
            # Rate limit
            rate = stats['rate_limit']
            msg += f"\n⏱️ **Rate Limit:**\n"
            msg += f"• Limite por minuto: {rate['limite_por_minuto']}\n"
            msg += f"• Utilização atual: {rate['utilizacao_atual']}\n"
            msg += f"• Status: {rate['status']}\n"
            
            # Estatísticas do banco (se disponível)
            if 'banco_dados' in stats and stats['banco_dados']:
                banco = stats['banco_dados']
                msg += f"\n🗄️ **Banco de Dados:**\n"
                
                if isinstance(banco, dict):
                    for key, value in banco.items():
                        if key != 'erro':
                            msg += f"• {key.replace('_', ' ').title()}: {value}\n"
            
            # Botões de ação
            keyboard = [
                [InlineKeyboardButton("🔄 Atualizar", callback_data="stats_completas")],
                [InlineKeyboardButton("🧹 Resetar Métricas", callback_data="resetar_metricas")],
                [InlineKeyboardButton("🔙 Status Sistema", callback_data="sistema_status")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(msg, parse_mode='Markdown', reply_markup=reply_markup)
            
        except Exception as e:
            logger.error(f"Erro no comando stats_avancado: {e}")
            await update.message.reply_text(f"❌ Erro ao obter estatísticas: {e}")
    
    async def processar_callback_stats(self, update, context: ContextTypes.DEFAULT_TYPE):
        """Processa callbacks das estatísticas"""
        query = update.callback_query
        await query.answer()
        
        if query.data == "stats_completas":
            # Reexecutar comando de stats
            await self.comando_stats_avancado(update, context)
        
        elif query.data == "resetar_metricas":
            try:
                self.notification_service.resetar_metricas()
                await query.edit_message_text(
                    "✅ **MÉTRICAS RESETADAS**\n\n"
                    "Todas as métricas da sessão atual foram zeradas.\n"
                    "O sistema está pronto para novas operações.",
                    parse_mode='Markdown'
                )
            except Exception as e:
                await query.edit_message_text(f"❌ Erro ao resetar métricas: {e}")
        
        elif query.data == "sistema_status":
            # Mostrar status do sistema
            await self.comando_sistema_status(update, context)
        
        elif query.data == "teste_conectividade":
            try:
                await query.edit_message_text(
                    "🧪 **TESTANDO CONECTIVIDADE**\n\n"
                    "⏳ Verificando todos os componentes...",
                    parse_mode='Markdown'
                )
                
                resultado = await self.notification_service.teste_conectividade_completo()
                
                msg = "🧪 **RESULTADO DO TESTE**\n\n"
                
                for componente, info in resultado['componentes'].items():
                    icon = "✅" if info['status'] else "❌"
                    nome = componente.replace('_', ' ').title()
                    msg += f"{icon} **{nome}:** {info['detalhes']}\n"
                
                status_geral = "✅ OPERACIONAL" if resultado['status_geral'] else "❌ PROBLEMAS"
                msg += f"\n🎯 **Status Geral:** {status_geral}"
                
                keyboard = [
                    [InlineKeyboardButton("🔄 Testar Novamente", callback_data="teste_conectividade")],
                    [InlineKeyboardButton("🔙 Voltar", callback_data="sistema_status")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(msg, parse_mode='Markdown', reply_markup=reply_markup)
                
            except Exception as e:
                await query.edit_message_text(f"❌ Erro no teste: {e}")
    
    async def comando_teste_whatsapp(self, update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /teste_whatsapp - Teste específico do WhatsApp"""
        try:
            if not context.args or len(context.args) < 2:
                msg = ("📱 **TESTE WHATSAPP**\n\n"
                      "Uso: `/teste_whatsapp [número] [mensagem]`\n\n"
                      "Exemplo:\n"
                      "`/teste_whatsapp 11999887766 Olá! Este é um teste.`\n\n"
                      "O número pode estar em qualquer formato:\n"
                      "• 11999887766\n"
                      "• (11) 99988-7766\n"
                      "• +55 11 99988-7766")
                
                await update.message.reply_text(msg, parse_mode='Markdown')
                return
            
            telefone = context.args[0]
            mensagem = " ".join(context.args[1:])
            
            # Mostrar progresso
            await update.message.reply_text(
                "📱 **ENVIANDO TESTE WHATSAPP**\n\n"
                f"📞 Número: {telefone}\n"
                f"💬 Mensagem: {mensagem[:50]}{'...' if len(mensagem) > 50 else ''}\n\n"
                "⏳ Processando...",
                parse_mode='Markdown'
            )
            
            # Enviar mensagem
            sucesso = await self.notification_service.enviar_mensagem_manual(telefone, mensagem, "Teste Manual")
            
            if sucesso:
                msg = ("✅ **TESTE ENVIADO COM SUCESSO**\n\n"
                      f"📞 Número: {telefone}\n"
                      f"💬 Mensagem enviada às {datetime.now().strftime('%H:%M:%S')}\n\n"
                      "🔍 Verifique o WhatsApp do destinatário.")
            else:
                msg = ("❌ **FALHA NO ENVIO**\n\n"
                      f"📞 Número: {telefone}\n"
                      f"⚠️ A mensagem não pôde ser enviada.\n\n"
                      "Possíveis causas:\n"
                      "• Número inválido\n"
                      "• WhatsApp desconectado\n"
                      "• Rate limit atingido\n"
                      "• Problema na Evolution API")
            
            keyboard = [
                [InlineKeyboardButton("🔄 Status Sistema", callback_data="sistema_status")],
                [InlineKeyboardButton("📊 Ver Estatísticas", callback_data="stats_completas")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(msg, parse_mode='Markdown', reply_markup=reply_markup)
            
        except Exception as e:
            logger.error(f"Erro no comando teste_whatsapp: {e}")
            await update.message.reply_text(f"❌ Erro no teste: {e}")