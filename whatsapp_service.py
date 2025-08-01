"""
Serviço de integração com Evolution API para WhatsApp
"""

import aiohttp
import asyncio
import logging
from typing import Optional, Dict
from config import EVOLUTION_API_URL, EVOLUTION_API_KEY, EVOLUTION_INSTANCE_NAME

logger = logging.getLogger(__name__)

class WhatsAppService:
    """Serviço para integração com Evolution API"""
    
    def __init__(self):
        # Garantir que a URL tenha protocolo
        if not EVOLUTION_API_URL.startswith(('http://', 'https://')):
            self.api_url = f"https://{EVOLUTION_API_URL.rstrip('/')}"
        else:
            self.api_url = EVOLUTION_API_URL.rstrip('/')
        self.api_key = EVOLUTION_API_KEY
        self.instance_name = EVOLUTION_INSTANCE_NAME
        self.session = None
    
    async def get_session(self):
        """Retorna uma sessão HTTP reutilizável"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session
    
    async def close_session(self):
        """Fecha a sessão HTTP"""
        if self.session and not self.session.closed:
            await self.session.close()
    
    def get_headers(self) -> Dict[str, str]:
        """Retorna os headers para requisições à Evolution API"""
        return {
            'Content-Type': 'application/json',
            'apikey': self.api_key
        }
    
    async def enviar_mensagem(self, telefone: str, mensagem: str) -> bool:
        """Envia mensagem via WhatsApp usando Evolution API"""
        try:
            session = await self.get_session()
            
            # Formatar o número de telefone
            numero_formatado = self.formatar_numero_whatsapp(telefone)
            
            # Dados da mensagem
            data = {
                "number": numero_formatado,
                "text": mensagem
            }
            
            # URL para envio de mensagem - garantir formato correto
            url = f"{self.api_url}/message/sendText/{self.instance_name}"
            logger.info(f"Enviando mensagem para {numero_formatado} via URL: {url}")
            
            async with session.post(url, json=data, headers=self.get_headers()) as response:
                if response.status == 200:
                    response_data = await response.json()
                    logger.info(f"Mensagem enviada para {telefone}: {response_data}")
                    return True
                else:
                    error_text = await response.text()
                    logger.error(f"Erro ao enviar mensagem para {telefone}: {response.status} - {error_text}")
                    return False
                    
        except Exception as e:
            logger.error(f"Exceção ao enviar mensagem para {telefone}: {str(e)}")
            logger.error(f"URL tentada: {self.api_url}/message/sendText/{self.instance_name}")
            logger.error(f"Configurações: API_URL={self.api_url}, INSTANCE={self.instance_name}")
            return False
    
    async def enviar_mensagem_com_midia(self, telefone: str, mensagem: str, 
                                       midia_url: str, tipo_midia: str = "image") -> bool:
        """Envia mensagem com mídia (imagem, documento, etc.)"""
        try:
            session = await self.get_session()
            
            numero_formatado = self.formatar_numero_whatsapp(telefone)
            
            # Dados da mensagem com mídia
            data = {
                "number": numero_formatado,
                "caption": mensagem,
                "media": midia_url
            }
            
            # Escolher endpoint baseado no tipo de mídia
            endpoint_map = {
                "image": "sendMedia",
                "document": "sendMedia",
                "audio": "sendMedia",
                "video": "sendMedia"
            }
            
            endpoint = endpoint_map.get(tipo_midia, "sendMedia")
            url = f"{self.api_url}/message/{endpoint}/{self.instance_name}"
            
            async with session.post(url, json=data, headers=self.get_headers()) as response:
                if response.status == 200:
                    response_data = await response.json()
                    logger.info(f"Mensagem com mídia enviada para {telefone}: {response_data}")
                    return True
                else:
                    error_text = await response.text()
                    logger.error(f"Erro ao enviar mídia para {telefone}: {response.status} - {error_text}")
                    return False
                    
        except Exception as e:
            logger.error(f"Exceção ao enviar mídia para {telefone}: {e}")
            return False
    
    async def verificar_status_instancia(self) -> Optional[Dict]:
        """Obtém informações detalhadas do status da instância"""
        try:
            session = await self.get_session()
            
            url = f"{self.api_url}/instance/connectionState/{self.instance_name}"
            logger.info(f"Verificando status via URL: {url}")
            
            async with session.get(url, 
                                 headers=self.get_headers(),
                                 allow_redirects=True,
                                 timeout=aiohttp.ClientTimeout(total=15)) as response:
                
                logger.info(f"Status da verificação: {response.status}")
                
                if response.status == 200:
                    data = await response.json()
                    logger.info(f"Status da instância {self.instance_name}: {data}")
                    return data.get('instance', {})
                elif response.status == 404:
                    logger.warning(f"Instância {self.instance_name} não existe")
                    return {'state': 'not_found', 'message': 'Instância não encontrada'}
                else:
                    error_text = await response.text()
                    logger.error(f"Erro ao verificar status da instância: {response.status} - {error_text}")
                    return {'state': 'error', 'message': f'Erro HTTP {response.status}'}
                    
        except Exception as e:
            logger.error(f"Exceção ao verificar status da instância: {e}")
            return {'state': 'error', 'message': str(e)}

    async def verificar_status(self) -> bool:
        """Verifica se a instância do WhatsApp está conectada"""
        try:
            session = await self.get_session()
            
            url = f"{self.api_url}/instance/connectionState/{self.instance_name}"
            
            async with session.get(url, headers=self.get_headers()) as response:
                if response.status == 200:
                    data = await response.json()
                    status = data.get('instance', {}).get('state', '')
                    
                    # Estados que indicam conexão ativa (mais rigoroso)
                    estados_conectados = ['open', 'connected']  # Removido 'connecting' para ser mais específico
                    conectado = status in estados_conectados
                    
                    logger.info(f"Status da instância {self.instance_name}: {status}")
                    return conectado
                else:
                    error_text = await response.text()
                    logger.error(f"Erro ao verificar status: {response.status} - {error_text}")
                    return False
                    
        except Exception as e:
            logger.error(f"Exceção ao verificar status: {e}")
            return False
    
    async def criar_instancia(self) -> bool:
        """Cria uma nova instância do WhatsApp com configurações estabilizadas"""
        try:
            session = await self.get_session()
            
            data = {
                "instanceName": self.instance_name,
                "qrcode": True,
                "integration": "WHATSAPP-BAILEYS",
                "rejectCall": False,
                "msgRetryCounterCache": True,
                "markMessagesRead": True,
                "alwaysOnline": True,
                "readMessages": True,
                "readStatus": True,
                "syncFullHistory": False,
                "webhookEvents": ["QRCODE_UPDATED", "CONNECTION_UPDATE", "MESSAGES_UPSERT"],
                "websocket": {
                    "events": ["QRCODE_UPDATED", "CONNECTION_UPDATE"]
                }
            }
            
            url = f"{self.api_url}/instance/create"
            logger.info(f"Criando instância via URL: {url} com dados: {data}")
            
            async with session.post(url, 
                                  json=data, 
                                  headers=self.get_headers(),
                                  timeout=aiohttp.ClientTimeout(total=30)) as response:
                
                logger.info(f"Status da criação: {response.status}")
                
                if response.status in [200, 201]:
                    response_data = await response.json()
                    logger.info(f"Instância criada: {response_data}")
                    return True
                else:
                    error_text = await response.text()
                    logger.error(f"Erro ao criar instância: {response.status} - {error_text}")
                    return False
                    
        except Exception as e:
            logger.error(f"Exceção ao criar instância: {e}")
            return False
    
    async def reiniciar_instancia(self) -> bool:
        """Reinicia a instância do WhatsApp"""
        try:
            session = await self.get_session()
            
            url = f"{self.api_url}/instance/restart/{self.instance_name}"
            
            async with session.post(url, headers=self.get_headers()) as response:
                if response.status == 200:
                    logger.info(f"Instância {self.instance_name} reiniciada com sucesso")
                    return True
                else:
                    error_text = await response.text()
                    logger.error(f"Erro ao reiniciar instância: {response.status} - {error_text}")
                    return False
                    
        except Exception as e:
            logger.error(f"Exceção ao reiniciar instância: {e}")
            return False
    
    async def logout_instancia(self) -> bool:
        """Desconecta a instância do WhatsApp"""
        try:
            session = await self.get_session()
            
            url = f"{self.api_url}/instance/logout/{self.instance_name}"
            
            async with session.post(url, headers=self.get_headers()) as response:
                if response.status == 200:
                    logger.info(f"Instância {self.instance_name} desconectada com sucesso")
                    return True
                else:
                    error_text = await response.text()
                    logger.error(f"Erro ao desconectar instância: {response.status} - {error_text}")
                    return False
                    
        except Exception as e:
            logger.error(f"Exceção ao desconectar instância: {e}")
            return False
    
    async def obter_qr_code(self) -> Optional[Dict]:
        """Obtém o QR Code para conexão"""
        try:
            session = await self.get_session()
            
            url = f"{self.api_url}/instance/connect/{self.instance_name}"
            logger.info(f"Solicitando QR Code via URL: {url}")
            
            async with session.get(url, headers=self.get_headers()) as response:
                if response.status == 200:
                    data = await response.json()
                    logger.info(f"Resposta QR Code: {data}")
                    return data
                else:
                    error_text = await response.text()
                    logger.error(f"Erro ao obter QR Code: {response.status} - {error_text}")
                    return None
                    
        except Exception as e:
            logger.error(f"Exceção ao obter QR Code: {e}")
            return None
    
    async def gerar_qr_code_base64(self) -> Optional[str]:
        """Gera novo QR Code e retorna em base64 validado"""
        try:
            session = await self.get_session()
            
            # Método 1: Tentar via endpoint connect (melhor prática Evolution API)
            connect_url = f"{self.api_url}/instance/connect/{self.instance_name}"
            logger.info(f"Tentando via connect: {connect_url}")
            
            try:
                async with session.get(connect_url, 
                                     headers=self.get_headers(),
                                     timeout=aiohttp.ClientTimeout(total=20)) as response:
                    
                    if response.status == 200:
                        data = await response.json()
                        logger.info(f"Connect response obtida: {list(data.keys()) if isinstance(data, dict) else type(data)}")
                        
                        qr_base64 = await self._extrair_qr_code_avancado(data)
                        if qr_base64:
                            validated = self.validar_e_limpar_base64(qr_base64)
                            if validated:
                                logger.info(f"✅ QR Code obtido via connect! Tamanho: {len(validated)}")
                                return validated
                    else:
                        logger.warning(f"Endpoint connect falhou: {response.status}")
                        
            except Exception as e:
                logger.warning(f"Método connect falhou: {e}")
            
            # Método 2: Tentar via endpoint direto de QR Code
            qr_url = f"{self.api_url}/instance/qrcode/{self.instance_name}"
            logger.info(f"Tentando via qrcode endpoint: {qr_url}")
            
            try:
                async with session.get(qr_url, 
                                     headers=self.get_headers(),
                                     timeout=aiohttp.ClientTimeout(total=15)) as response:
                    
                    if response.status == 200:
                        data = await response.json()
                        logger.info(f"QR endpoint response: {list(data.keys()) if isinstance(data, dict) else type(data)}")
                        
                        qr_base64 = await self._extrair_qr_code_avancado(data)
                        if qr_base64:
                            validated = self.validar_e_limpar_base64(qr_base64)
                            if validated:
                                logger.info(f"✅ QR Code obtido via qrcode endpoint! Tamanho: {len(validated)}")
                                return validated
                    else:
                        logger.warning(f"QR endpoint falhou: {response.status}")
                        
            except Exception as e:
                logger.warning(f"Método qrcode endpoint falhou: {e}")
            
            # Método 3: MÉTODO COMPROVADO - Restart da instância com validação
            logger.info("Executando restart da instância (método comprovado)...")
            restart_url = f"{self.api_url}/instance/restart/{self.instance_name}"
            
            async with session.post(restart_url, 
                                  headers=self.get_headers(),
                                  timeout=aiohttp.ClientTimeout(total=25)) as response:
                
                logger.info(f"Status da resposta restart: {response.status}")
                
                if response.status in [200, 201]:
                    data = await response.json()
                    logger.info(f"✅ Restart executado com sucesso")
                    
                    # Extrair QR Code da resposta do restart usando método avançado
                    qr_base64 = await self._extrair_qr_code_avancado(data)
                    if qr_base64:
                        validated = self.validar_e_limpar_base64(qr_base64)
                        if validated:
                            logger.info(f"✅ QR Code obtido via restart! Tamanho: {len(validated)}")
                            return validated
                    
                    # Se não veio direto, aguardar e verificar status múltiplas vezes
                    for tentativa in range(3):
                        logger.info(f"QR Code não veio direto, verificando status... (tentativa {tentativa + 1})")
                        await asyncio.sleep(2 + tentativa)  # Aumentar timeout a cada tentativa
                        
                        status_check_url = f"{self.api_url}/instance/connectionState/{self.instance_name}"
                        try:
                            async with session.get(status_check_url, 
                                                 headers=self.get_headers(),
                                                 timeout=aiohttp.ClientTimeout(total=15)) as status_response:
                                
                                if status_response.status == 200:
                                    status_data = await status_response.json()
                                    qr_base64 = await self._extrair_qr_code_avancado(status_data)
                                    if qr_base64:
                                        validated = self.validar_e_limpar_base64(qr_base64)
                                        if validated:
                                            logger.info(f"✅ QR Code obtido via status após restart (tentativa {tentativa + 1})!")
                                            return validated
                        except Exception as e:
                            logger.warning(f"Erro na verificação de status tentativa {tentativa + 1}: {e}")
                
                # Se restart não funcionou, tentar criar instância limpa
                logger.info("Restart não retornou QR Code válido, tentando instância limpa...")
                await self._deletar_e_recriar_instancia()
                await asyncio.sleep(3)
                
                # Tentar restart novamente na instância limpa
                async with session.post(restart_url, 
                                      headers=self.get_headers(),
                                      timeout=aiohttp.ClientTimeout(total=25)) as clean_response:
                    
                    if clean_response.status in [200, 201]:
                        clean_data = await clean_response.json()
                        qr_base64 = await self._extrair_qr_code_avancado(clean_data)
                        if qr_base64:
                            validated = self.validar_e_limpar_base64(qr_base64)
                            if validated:
                                logger.info(f"✅ QR Code obtido via restart em instância limpa!")
                                return validated
                
                logger.warning("QR Code não obtido com todos os métodos")
                return None
                    
        except Exception as e:
            logger.error(f"Exceção ao gerar QR Code: {e}")
            return None
    
    async def _extrair_qr_code_avancado(self, data: dict) -> Optional[str]:
        """Extrai QR Code de diferentes formatos de resposta da Evolution API"""
        if not isinstance(data, dict):
            return None
            
        # Lista de possíveis caminhos onde o QR Code pode estar
        qr_paths = [
            # Formatos padrão
            'qrcode', 'qr', 'base64',
            # Formatos aninhados
            ['qrcode', 'base64'], ['qrcode', 'code'], ['qrcode', 'data'],
            ['qr', 'base64'], ['qr', 'code'], ['qr', 'data'],
            ['instance', 'qrcode'], ['instance', 'qr'],
            ['instance', 'qrcode', 'base64'], ['instance', 'qrcode', 'code'],
            # Formatos específicos Evolution API
            ['connection', 'qrcode'], ['status', 'qr'], ['whatsapp', 'qr']
        ]
        
        for path in qr_paths:
            try:
                current_data = data
                if isinstance(path, list):
                    # Navegar através de estrutura aninhada
                    for key in path:
                        if isinstance(current_data, dict) and key in current_data:
                            current_data = current_data[key]
                        else:
                            current_data = None
                            break
                else:
                    # Chave simples
                    current_data = data.get(path) if isinstance(data, dict) else None
                
                if current_data and isinstance(current_data, str):
                    # Limpar prefixo data:image se presente
                    if current_data.startswith('data:image'):
                        current_data = current_data.split(',')[1]
                    
                    # Remover espaços e quebras de linha do base64
                    current_data = current_data.replace(' ', '').replace('\n', '').replace('\r', '').strip()
                    
                    # Verificar se é um base64 válido (melhorado)
                    if len(current_data) > 100:
                        # Validação mais robusta para base64
                        # Usar função de validação robusta
                        validated_base64 = self.validar_e_limpar_base64(current_data)
                        if validated_base64:
                            logger.info(f"QR Code encontrado e validado via path: {path}")
                            return validated_base64
                        
            except Exception as e:
                logger.debug(f"Erro ao extrair via path {path}: {e}")
                continue
        
        logger.warning(f"QR Code não encontrado em: {list(data.keys())}")
        return None
    
    async def _extrair_qr_code(self, data: dict) -> Optional[str]:
        """Método compatível com versão anterior"""
        return await self._extrair_qr_code_avancado(data)
    
    async def _deletar_e_recriar_instancia(self) -> bool:
        """Deleta e recria instância para garantir estado limpo"""
        try:
            session = await self.get_session()
            
            # Deletar instância existente
            delete_url = f"{self.api_url}/instance/delete/{self.instance_name}"
            async with session.delete(delete_url, 
                                    headers=self.get_headers(),
                                    timeout=aiohttp.ClientTimeout(total=15)) as response:
                if response.status == 200:
                    logger.info("Instância anterior deletada para recriação")
                    
            await asyncio.sleep(2)
            
            # Recriar instância com configurações estabilizadas
            create_data = {
                "instanceName": self.instance_name,
                "qrcode": True,
                "integration": "WHATSAPP-BAILEYS",
                "rejectCall": False,
                "msgRetryCounterCache": True,
                "markMessagesRead": True,
                "alwaysOnline": True,
                "readMessages": True,
                "readStatus": True,
                "syncFullHistory": False,
                "webhookEvents": ["QRCODE_UPDATED", "CONNECTION_UPDATE", "MESSAGES_UPSERT"],
                "websocket": {
                    "events": ["QRCODE_UPDATED", "CONNECTION_UPDATE"]
                }
            }
            
            create_url = f"{self.api_url}/instance/create"
            async with session.post(create_url, 
                                  headers=self.get_headers(),
                                  json=create_data,
                                  timeout=aiohttp.ClientTimeout(total=30)) as response:
                
                if response.status in [200, 201]:
                    logger.info("Instância limpa criada com sucesso")
                    return True
                else:
                    logger.warning(f"Falha ao recriar instância: {response.status}")
                    return False
            
        except Exception as e:
            logger.error(f"Erro ao deletar e recriar instância: {e}")
            return False
    

    
    async def aguardar_conexao_estavel(self, timeout: int = 60) -> bool:
        """Aguarda até que a conexão WhatsApp esteja estável"""
        import asyncio
        
        logger.info(f"Aguardando conexão estável por até {timeout} segundos...")
        
        for tentativa in range(timeout // 5):  # Verificar a cada 5 segundos
            try:
                status = await self.verificar_status_instancia()
                if status:
                    state = status.get('state', '')
                    logger.info(f"Tentativa {tentativa + 1}: Estado = {state}")
                    
                    if state == 'open':
                        logger.info("✅ Conexão WhatsApp estabilizada!")
                        return True
                    elif state in ['close', 'connecting']:
                        logger.info(f"Estado {state}, continuando aguardar...")
                    else:
                        logger.warning(f"Estado desconhecido: {state}")
                
                await asyncio.sleep(5)
                
            except Exception as e:
                logger.error(f"Erro ao verificar conexão (tentativa {tentativa + 1}): {e}")
                await asyncio.sleep(5)
        
        logger.warning(f"Timeout de {timeout}s atingido, conexão não estabilizada")
        return False

    async def reconectar_instancia(self) -> bool:
        """Força uma reconexão da instância com aguardo de estabilização"""
        try:
            logger.info("Iniciando processo de reconexão...")
            
            # 1. Desconectar se estiver conectado
            await self.logout_instancia()
            await asyncio.sleep(3)
            
            # 2. Deletar e recriar instância
            await self._deletar_e_recriar_instancia()
            await asyncio.sleep(5)
            
            # 3. Gerar novo QR Code
            qr_code = await self.gerar_qr_code_base64()
            if not qr_code:
                logger.error("Falha ao gerar QR Code após reconexão")
                return False
            
            logger.info("QR Code gerado, aguardando que seja escaneado...")
            
            # 4. Aguardar conexão estável
            conexao_ok = await self.aguardar_conexao_estavel(90)  # 90 segundos para escanear
            
            if conexao_ok:
                logger.info("✅ Reconexão bem-sucedida!")
                return True
            else:
                logger.warning("❌ Reconexão falhou - QR Code não foi escaneado ou conexão instável")
                return False
                
        except Exception as e:
            logger.error(f"Erro durante reconexão: {e}")
            return False

    def validar_e_limpar_base64(self, base64_string: str) -> Optional[str]:
        """Valida e limpa string base64 para garantir formato correto"""
        try:
            if not base64_string:
                return None
                
            # Remover espaços, quebras de linha e caracteres invisíveis
            cleaned = base64_string.replace(' ', '').replace('\n', '').replace('\r', '').replace('\t', '').strip()
            
            # Verificar se tem prefixo data:image e remover
            if cleaned.startswith('data:image'):
                cleaned = cleaned.split(',')[1]
            
            # Adicionar padding se necessário para o base64
            missing_padding = len(cleaned) % 4
            if missing_padding:
                cleaned += '=' * (4 - missing_padding)
            
            # Validar se pode ser decodificado
            import base64
            base64.b64decode(cleaned, validate=True)
            
            logger.info(f"Base64 validado e limpo. Tamanho: {len(cleaned)}")
            return cleaned
            
        except Exception as e:
            logger.error(f"Erro ao validar base64: {e}")
            return None

    def formatar_numero_whatsapp(self, telefone: str) -> str:
        """Formata o número de telefone para o formato do WhatsApp"""
        # Remove caracteres não numéricos
        numero_limpo = ''.join(filter(str.isdigit, telefone))
        
        # Se o número tem 11 dígitos e começa com 0, remove o 0
        if len(numero_limpo) == 11 and numero_limpo.startswith('0'):
            numero_limpo = numero_limpo[1:]
        
        # Se o número tem 10 dígitos, adiciona o 9 após o código de área
        if len(numero_limpo) == 10:
            # Código de área (2 primeiros dígitos) + 9 + restante
            numero_limpo = numero_limpo[:2] + '9' + numero_limpo[2:]
        
        # Adiciona código do país (Brasil +55) se não estiver presente
        if not numero_limpo.startswith('55'):
            numero_limpo = '55' + numero_limpo
        
        return numero_limpo
    
    async def obter_info_contato(self, telefone: str) -> Optional[Dict]:
        """Obtém informações sobre um contato"""
        try:
            session = await self.get_session()
            
            numero_formatado = self.formatar_numero_whatsapp(telefone)
            
            url = f"{self.api_url}/chat/findContact/{self.instance_name}"
            data = {"number": numero_formatado}
            
            async with session.post(url, json=data, headers=self.get_headers()) as response:
                if response.status == 200:
                    contact_data = await response.json()
                    return contact_data
                else:
                    error_text = await response.text()
                    logger.error(f"Erro ao obter info do contato {telefone}: {response.status} - {error_text}")
                    return None
                    
        except Exception as e:
            logger.error(f"Exceção ao obter info do contato {telefone}: {e}")
            return None
    
    async def verificar_numero_existe(self, telefone: str) -> bool:
        """Verifica se um número existe no WhatsApp"""
        try:
            info_contato = await self.obter_info_contato(telefone)
            return info_contato is not None and info_contato.get('exists', False)
        except Exception as e:
            logger.error(f"Erro ao verificar número {telefone}: {e}")
            return False
    
    def __del__(self):
        """Destrutor para fechar a sessão"""
        if hasattr(self, 'session') and self.session and not self.session.closed:
            # Como estamos em um destrutor, precisamos usar asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(self.close_session())
                else:
                    loop.run_until_complete(self.close_session())
            except:
                pass  # Ignorar erros no destructor
