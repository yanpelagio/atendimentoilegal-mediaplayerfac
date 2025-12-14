# 🤖 Bot de Atendimento e Monitoramento

Bot Discord combinado com duas funcionalidades principais:

## 🎯 Funcionalidades

### 1. Sistema de Atendimento Automático
- Detecta quando membros entram em canais de voz específicos
- Cria registros automáticos de atendimento
- Interface com botões para preenchimento
- Modal para detalhar o motivo do atendimento
- Sistema de auxiliares e responsáveis

### 2. Sistema de Monitoramento de Players
- Monitora mensagens em canais específicos
- Processa estatísticas de facções
- Painel interativo com TOP 5 facções
- Banco de dados SQLite para armazenamento
- Atualização automática a cada 5 minutos

## ⚙️ Configuração

### Variáveis de Ambiente no Square Cloud:
- `DISCORD_TOKEN`: Token do seu bot Discord

### IDs dos Canais (Configurar no código):
Edite as constantes no início do `main.py`:
- `CANAL_ORIGEM_ID`
- `CANAIS_ATENDIMENTO_IDS`
- `CANAL_REGISTRO_ID`
- `CANAL_ENTRADA_ID`
- `CANAL_FACCOES_ID`
- `CANAL_PAINEL_ID`

## 🚀 Deploy no Square Cloud

1. Conecte este repositório no Square Cloud
2. Configure a variável de ambiente `DISCORD_TOKEN`
3. Deploy automático via GitHub

## 📊 Estrutura do Banco de Dados

O bot usa SQLite com duas tabelas:
- `faccoes`: Armazena informações das facções
- `registros_players`: Armazena histórico de players online
