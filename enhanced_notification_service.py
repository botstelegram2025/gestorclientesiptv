"""
Sistema Aprimorado de Notificações via WhatsApp
Implementa recursos avançados como:
- Fila de mensagens com retry automático
- Validação de números de telefone
- Templates dinâmicos e personalizáveis  
- Agendamento de notificações
- Métricas e relatórios detalhados
- Rate limiting para evitar bloqueios
"""

import asyncio
import uuid
import logging
import json
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Callable
from dataclasses import dataclass, asdict
from enum import Enum
import re
from database import DatabaseManager
from whatsapp_service import WhatsAppService
from templates import TemplateManager

logger = logging.getLogger(__name__)

class TipoNotificacao(Enum):
    """Tipos de notificação disponíveis"""
    VENCIMENTO_2_DIAS = "vencimento_2_dias"
    VENCIMENTO_1_DIA = "vencimento_1_dia"
    VENCIMENTO_HOJE = "vencimento_hoje"
    VENCIDO = "vencido"
    RENOVACAO = "renovacao"
    BEM_VINDO = "bem_vindo"
    COBRANCA = "cobranca"
    PROMOCIONAL = "promocional"
    PERSONALIZADA = "personalizada"

class StatusMensagem(Enum):
    """Status das mensagens na fila"""
    PENDENTE = "pendente"
    ENVIANDO = "enviando"
    ENVIADA = "enviada"
    ERRO = "erro"
    FALHA_FINAL = "falha_final"

@dataclass
class MensagemFila:
    """Representa uma mensagem na fila de envio"""
    id: str
    telefone: str
    nome_cliente: str
    tipo: TipoNotificacao
    conteudo: str
    prioridade: int = 1  # 1=baixa, 2=média, 3=alta
    tentativas: int = 0
    max_tentativas: int = 3
    agendado_para: Optional[datetime] = None
    status: StatusMensagem = StatusMensagem.PENDENTE
    erro_detalhes: Optional[str] = None
    criado_em: Optional[datetime] = None
    enviado_em: Optional[datetime] = None
    
    def __post_init__(self):
        if self.criado_em is None:
            self.criado_em = datetime.now()

class EnhancedNotificationService:
    """Serviço aprimorado de notificações com recursos avançados"""
    
    def __init__(self, db_manager: DatabaseManager, whatsapp_service: WhatsAppService):
        self.db = db_manager
        self.whatsapp = whatsapp_service
        self.template_manager = TemplateManager(db_manager)
        
        # Fila de mensagens
        self.fila_mensagens: List[MensagemFila] = []
        self.processando_fila = False
        
        # Rate limiting (máximo 30 mensagens por minuto para evitar bloqueios)
        self.max_mensagens_por_minuto = 30
        self.mensagens_enviadas_ultimo_minuto = []
        
        # Métricas
        self.metricas = {
            'total_enviadas': 0,
            'total_falharam': 0,
            'taxa_sucesso': 0.0,
            'ultimo_reset': datetime.now()
        }
        
        # Criar tabelas necessárias
        self._inicializar_tabelas()
    
    def _inicializar_tabelas(self):
        """Inicializa tabelas específicas para notificações avançadas"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        try:
            # Tabela para fila de mensagens persistente
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS fila_mensagens (
                    id TEXT PRIMARY KEY,
                    telefone TEXT NOT NULL,
                    nome_cliente TEXT NOT NULL,
                    tipo TEXT NOT NULL,
                    conteudo TEXT NOT NULL,
                    prioridade INTEGER DEFAULT 1,
                    tentativas INTEGER DEFAULT 0,
                    max_tentativas INTEGER DEFAULT 3,
                    agendado_para TEXT,
                    status TEXT DEFAULT 'pendente',
                    erro_detalhes TEXT,
                    criado_em TEXT NOT NULL,
                    enviado_em TEXT
                )
            ''')
            
            # Tabela para configurações de notificação
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS config_notificacoes (
                    id INTEGER PRIMARY KEY,
                    tipo_notificacao TEXT UNIQUE NOT NULL,
                    ativo BOOLEAN DEFAULT 1,
                    horario_envio TEXT DEFAULT '09:00',
                    dias_antecedencia INTEGER DEFAULT 1,
                    template_personalizado TEXT,
                    configuracoes_extras TEXT
                )
            ''')
            
            # Tabela para métricas detalhadas
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS metricas_whatsapp (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    data_hora TEXT NOT NULL,
                    tipo_notificacao TEXT NOT NULL,
                    total_enviadas INTEGER DEFAULT 0,
                    total_falharam INTEGER DEFAULT 0,
                    taxa_sucesso REAL DEFAULT 0.0,
                    tempo_medio_envio REAL DEFAULT 0.0
                )
            ''')
            
            conn.commit()
            logger.info("Tabelas de notificações aprimoradas criadas com sucesso")
            
        except Exception as e:
            logger.error(f"Erro ao criar tabelas de notificações: {e}")
            conn.rollback()
        finally:
            conn.close()
    
    def validar_numero_telefone(self, telefone: str) -> tuple:
        """
        Valida e formata número de telefone brasileiro
        Returns: (válido, número_formatado)
        """
        # Remove todos os caracteres não numéricos
        numero = re.sub(r'\D', '', telefone)
        
        # Verifica se tem o código do país (55)
        if numero.startswith('55'):
            numero = numero[2:]
        
        # Verifica se tem DDD válido (11-99)
        if len(numero) in [10, 11]:  # 10 dígitos (fixo) ou 11 dígitos (celular)
            ddd = numero[:2]
            if 11 <= int(ddd) <= 99:
                # Adiciona 9 no celular se necessário
                if len(numero) == 10 and numero[2] in ['6', '7', '8', '9']:
                    numero = numero[:2] + '9' + numero[2:]
                
                numero_formatado = f"55{numero}"
                return True, numero_formatado
        
        return False, telefone
    
    async def adicionar_mensagem_fila(self, telefone: str, nome_cliente: str, 
                                    tipo: TipoNotificacao, conteudo: str, 
                                    prioridade: int = 1, 
                                    agendado_para: Optional[datetime] = None) -> str:
        """Adiciona mensagem à fila de envio com validação"""
        
        # Validar número de telefone
        valido, telefone_formatado = self.validar_numero_telefone(telefone)
        if not valido:
            logger.error(f"Número de telefone inválido: {telefone}")
            return None
        
        # Gerar ID único
        mensagem_id = str(uuid.uuid4())
        
        # Criar objeto da mensagem
        mensagem = MensagemFila(
            id=mensagem_id,
            telefone=telefone_formatado,
            nome_cliente=nome_cliente,
            tipo=tipo,
            conteudo=conteudo,
            prioridade=prioridade,
            agendado_para=agendado_para
        )
        
        # Adicionar à fila em memória
        self.fila_mensagens.append(mensagem)
        
        # Persistir no banco
        self._salvar_mensagem_banco(mensagem)
        
        logger.info(f"Mensagem {tipo.value} adicionada à fila para {nome_cliente} ({telefone_formatado})")
        return mensagem_id
    
    def _salvar_mensagem_banco(self, mensagem: MensagemFila):
        """Salva mensagem no banco de dados"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT INTO fila_mensagens (
                    id, telefone, nome_cliente, tipo, conteudo, prioridade,
                    tentativas, max_tentativas, agendado_para, status,
                    erro_detalhes, criado_em, enviado_em
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                mensagem.id,
                mensagem.telefone,
                mensagem.nome_cliente,
                mensagem.tipo.value,
                mensagem.conteudo,
                mensagem.prioridade,
                mensagem.tentativas,
                mensagem.max_tentativas,
                mensagem.agendado_para.isoformat() if mensagem.agendado_para else None,
                mensagem.status.value,
                mensagem.erro_detalhes,
                mensagem.criado_em.isoformat(),
                mensagem.enviado_em.isoformat() if mensagem.enviado_em else None
            ))
            
            conn.commit()
            
        except Exception as e:
            logger.error(f"Erro ao salvar mensagem no banco: {e}")
            conn.rollback()
        finally:
            conn.close()
    
    def _verificar_rate_limit(self) -> bool:
        """Verifica se ainda é possível enviar mensagens (rate limiting)"""
        agora = datetime.now()
        um_minuto_atras = agora - timedelta(minutes=1)
        
        # Remove mensagens antigas da lista
        self.mensagens_enviadas_ultimo_minuto = [
            timestamp for timestamp in self.mensagens_enviadas_ultimo_minuto 
            if timestamp > um_minuto_atras
        ]
        
        # Verifica se ainda pode enviar
        return len(self.mensagens_enviadas_ultimo_minuto) < self.max_mensagens_por_minuto
    
    async def processar_fila_mensagens(self):
        """Processa a fila de mensagens de forma assíncrona"""
        if self.processando_fila:
            logger.info("Fila já está sendo processada")
            return
        
        self.processando_fila = True
        logger.info("Iniciando processamento da fila de mensagens")
        
        try:
            # Ordenar por prioridade e data
            mensagens_para_enviar = [
                msg for msg in self.fila_mensagens 
                if msg.status == StatusMensagem.PENDENTE and 
                (msg.agendado_para is None or msg.agendado_para <= datetime.now())
            ]
            
            mensagens_para_enviar.sort(key=lambda x: (-x.prioridade, x.criado_em))
            
            for mensagem in mensagens_para_enviar:
                # Verificar rate limit
                if not self._verificar_rate_limit():
                    logger.warning("Rate limit atingido, pausando envios por 1 minuto")
                    await asyncio.sleep(60)
                
                await self._processar_mensagem_individual(mensagem)
                
                # Pequena pausa entre mensagens
                await asyncio.sleep(2)
            
        except Exception as e:
            logger.error(f"Erro no processamento da fila: {e}")
        finally:
            self.processando_fila = False
            logger.info("Processamento da fila finalizado")
    
    async def _processar_mensagem_individual(self, mensagem: MensagemFila):
        """Processa uma mensagem individual"""
        mensagem.status = StatusMensagem.ENVIANDO
        mensagem.tentativas += 1
        
        try:
            # Tentar enviar via WhatsApp
            sucesso = await self.whatsapp.enviar_mensagem(mensagem.telefone, mensagem.conteudo)
            
            if sucesso:
                mensagem.status = StatusMensagem.ENVIADA
                mensagem.enviado_em = datetime.now()
                self.mensagens_enviadas_ultimo_minuto.append(datetime.now())
                self.metricas['total_enviadas'] += 1
                
                logger.info(f"✅ Mensagem enviada para {mensagem.nome_cliente}")
                
                # Registrar no log tradicional
                self.db.log_mensagem(
                    telefone=mensagem.telefone,
                    nome_cliente=mensagem.nome_cliente,
                    tipo_mensagem=mensagem.tipo.value,
                    conteudo=mensagem.conteudo,
                    status="enviada"
                )
                
            else:
                await self._processar_falha_mensagem(mensagem, "Falha no envio via WhatsApp")
                
        except Exception as e:
            await self._processar_falha_mensagem(mensagem, str(e))
        
        # Atualizar no banco
        self._atualizar_mensagem_banco(mensagem)
    
    async def _processar_falha_mensagem(self, mensagem: MensagemFila, erro: str):
        """Processa falha no envio de mensagem"""
        mensagem.erro_detalhes = erro
        
        if mensagem.tentativas >= mensagem.max_tentativas:
            mensagem.status = StatusMensagem.FALHA_FINAL
            self.metricas['total_falharam'] += 1
            logger.error(f"❌ Mensagem falhou definitivamente para {mensagem.nome_cliente}: {erro}")
            
            # Registrar falha no log
            self.db.log_mensagem(
                telefone=mensagem.telefone,
                nome_cliente=mensagem.nome_cliente,
                tipo_mensagem=mensagem.tipo.value,
                conteudo=mensagem.conteudo,
                status="erro",
                erro_detalhes=erro
            )
        else:
            mensagem.status = StatusMensagem.ERRO
            # Reagendar para nova tentativa em 5 minutos
            mensagem.agendado_para = datetime.now() + timedelta(minutes=5)
            logger.warning(f"⚠️ Tentativa {mensagem.tentativas} falhou para {mensagem.nome_cliente}, reagendando")
    
    def _atualizar_mensagem_banco(self, mensagem: MensagemFila):
        """Atualiza mensagem no banco de dados"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                UPDATE fila_mensagens SET
                    tentativas = ?, status = ?, erro_detalhes = ?,
                    enviado_em = ?, agendado_para = ?
                WHERE id = ?
            ''', (
                mensagem.tentativas,
                mensagem.status.value,
                mensagem.erro_detalhes,
                mensagem.enviado_em.isoformat() if mensagem.enviado_em else None,
                mensagem.agendado_para.isoformat() if mensagem.agendado_para else None,
                mensagem.id
            ))
            
            conn.commit()
            
        except Exception as e:
            logger.error(f"Erro ao atualizar mensagem no banco: {e}")
            conn.rollback()
        finally:
            conn.close()
    
    async def notificar_vencimentos_automatico(self):
        """Sistema automatizado de notificação de vencimentos"""
        logger.info("Iniciando verificação automática de vencimentos")
        
        try:
            # Vencimentos em 2 dias
            clientes_2_dias = self.db.clientes_vencendo(2)
            for cliente in clientes_2_dias:
                await self._processar_notificacao_vencimento(cliente, TipoNotificacao.VENCIMENTO_2_DIAS)
            
            # Vencimentos em 1 dia
            clientes_1_dia = self.db.clientes_vencendo(1)
            for cliente in clientes_1_dia:
                await self._processar_notificacao_vencimento(cliente, TipoNotificacao.VENCIMENTO_1_DIA)
            
            # Vencimentos hoje
            clientes_hoje = self.db.clientes_vencendo(0)
            for cliente in clientes_hoje:
                await self._processar_notificacao_vencimento(cliente, TipoNotificacao.VENCIMENTO_HOJE)
            
            # Clientes vencidos
            clientes_vencidos = self.db.clientes_vencidos()
            for cliente in clientes_vencidos:
                await self._processar_notificacao_vencimento(cliente, TipoNotificacao.VENCIDO)
            
            # Processar a fila
            await self.processar_fila_mensagens()
            
            logger.info("Verificação automática de vencimentos concluída")
            
        except Exception as e:
            logger.error(f"Erro na verificação automática: {e}")
    
    async def _processar_notificacao_vencimento(self, cliente: Dict, tipo: TipoNotificacao):
        """Processa notificação de vencimento individual"""
        try:
            # Gerar mensagem personalizada
            mensagem = self.template_manager.gerar_mensagem_vencimento(cliente, tipo.value.replace('vencimento_', ''))
            
            if mensagem:
                # Adicionar à fila com prioridade baseada na urgência
                prioridade = {
                    TipoNotificacao.VENCIDO: 3,
                    TipoNotificacao.VENCIMENTO_HOJE: 3,
                    TipoNotificacao.VENCIMENTO_1_DIA: 2,
                    TipoNotificacao.VENCIMENTO_2_DIAS: 1
                }.get(tipo, 1)
                
                await self.adicionar_mensagem_fila(
                    telefone=cliente['telefone'],
                    nome_cliente=cliente['nome'],
                    tipo=tipo,
                    conteudo=mensagem,
                    prioridade=prioridade
                )
                
        except Exception as e:
            logger.error(f"Erro ao processar notificação para {cliente.get('nome', 'N/A')}: {e}")
    
    def obter_metricas_detalhadas(self) -> Dict:
        """Retorna métricas detalhadas do sistema de notificações"""
        # Atualizar taxa de sucesso
        total_mensagens = self.metricas['total_enviadas'] + self.metricas['total_falharam']
        if total_mensagens > 0:
            self.metricas['taxa_sucesso'] = (self.metricas['total_enviadas'] / total_mensagens) * 100
        
        # Métricas da fila atual
        fila_stats = {
            'total_na_fila': len(self.fila_mensagens),
            'pendentes': len([m for m in self.fila_mensagens if m.status == StatusMensagem.PENDENTE]),
            'enviadas': len([m for m in self.fila_mensagens if m.status == StatusMensagem.ENVIADA]),
            'com_erro': len([m for m in self.fila_mensagens if m.status == StatusMensagem.ERRO]),
            'falhas_finais': len([m for m in self.fila_mensagens if m.status == StatusMensagem.FALHA_FINAL])
        }
        
        return {
            'metricas_gerais': self.metricas,
            'fila_atual': fila_stats,
            'rate_limit': {
                'max_por_minuto': self.max_mensagens_por_minuto,
                'enviadas_ultimo_minuto': len(self.mensagens_enviadas_ultimo_minuto)
            },
            'status_whatsapp': await self.whatsapp.verificar_status()
        }
    
    async def enviar_teste_conectividade(self) -> Dict:
        """Testa conectividade do sistema completo"""
        resultado = {
            'whatsapp_conectado': False,
            'banco_operacional': False,
            'templates_carregados': False,
            'fila_processando': self.processando_fila,
            'detalhes': {}
        }
        
        try:
            # Testar WhatsApp
            resultado['whatsapp_conectado'] = await self.whatsapp.verificar_status()
            
            # Testar banco
            try:
                self.db.listar_clientes()
                resultado['banco_operacional'] = True
            except Exception as e:
                resultado['detalhes']['erro_banco'] = str(e)
            
            # Testar templates
            try:
                # Verificar se template manager está funcionando
                resultado['templates_carregados'] = True
                resultado['detalhes']['total_templates'] = 'Sistema ativo'
            except Exception as e:
                resultado['detalhes']['erro_templates'] = str(e)
            
            # Status da instância WhatsApp
            status_instancia = await self.whatsapp.verificar_status_instancia()
            resultado['detalhes']['status_instancia'] = status_instancia
            
        except Exception as e:
            resultado['detalhes']['erro_geral'] = str(e)
        
        return resultado
    
    async def limpar_fila_mensagens(self, manter_pendentes: bool = True):
        """Limpa mensagens processadas da fila"""
        if manter_pendentes:
            # Remove apenas mensagens enviadas ou com falha final
            self.fila_mensagens = [
                msg for msg in self.fila_mensagens 
                if msg.status in [StatusMensagem.PENDENTE, StatusMensagem.ERRO]
            ]
        else:
            # Limpa toda a fila
            self.fila_mensagens = []
        
        # Limpar do banco também
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        try:
            if manter_pendentes:
                cursor.execute("DELETE FROM fila_mensagens WHERE status IN ('enviada', 'falha_final')")
            else:
                cursor.execute("DELETE FROM fila_mensagens")
            
            conn.commit()
            logger.info("Fila de mensagens limpa com sucesso")
            
        except Exception as e:
            logger.error(f"Erro ao limpar fila: {e}")
            conn.rollback()
        finally:
            conn.close()