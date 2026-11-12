# ✈️ Radar de Milhas Azul

Monitora oportunidades para usar pontos **Azul Fidelidade** e avisa no **Telegram**:

1. **Promoções**: lê os blogs de milhas (Pontos pra Voar, Passageiro de Primeira, Melhores Destinos, Mestre das Milhas) a cada 3h e avisa quando aparece algo da Azul. Cada aviso vem etiquetado: 🌎 Internacional, 💸 Desconto, 🔁 Bônus, 🚨 Alerta de passagem. **Grátis.**
2. **Assentos-prêmio**: consulta a disponibilidade da Azul (via Seats.aero) para voos saindo do Brasil para **América do Norte, Europa e América do Sul**, guarda o histórico de preços e avisa quando:
   - o preço fica **abaixo do teto** que você definir, ou
   - o preço cai **25% abaixo da mediana** daquela rota.
   Precisa do plano Pro do Seats.aero (cerca de US$10–13/mês).
3. **Painel web** com todas as ofertas, filtros e gráfico de tendência por rota.

Tudo roda de graça no GitHub (Actions + Pages). Você não precisa deixar computador ligado.

---

## Passo a passo (≈ 20 min)

### 1. Criar o bot do Telegram
1. No Telegram, procure **@BotFather** → **Iniciar**.
2. Envie `/newbot` → escolha um nome (ex: *Radar Milhas Vini*) → escolha um usuário terminando em `bot` (ex: `radarmilhasvini_bot`).
3. O BotFather responde com um **token** (tipo `7123456789:AAH...`). **Copie e guarde.**
4. Abra o seu bot novo (clique no link que o BotFather mandou) e clique em **Iniciar** / mande um "oi".
5. No navegador, abra: `https://api.telegram.org/bot<SEU_TOKEN>/getUpdates`
   (troque `<SEU_TOKEN>` pelo token).
6. Procure `"chat":{"id":` e copie o número que vem depois (ex: `123456789`). Esse é o **chat id**.

> Quer receber num grupo? Crie o grupo, adicione o bot, mande uma mensagem no grupo e repita o passo 5. O id do grupo começa com `-`.

### 2. Criar o repositório no GitHub
1. Crie uma conta em **github.com** (se ainda não tiver).
2. Clique em **+** (canto superior direito) → **New repository**.
3. Nome: `radar-milhas` · marque **Public** (o Pages grátis exige público; não há senha nem dado pessoal no repositório) → **Create repository**.
4. Na página do repositório: **Add file → Upload files**.
5. Descompacte o zip e **arraste todo o conteúdo da pasta `radar-milhas`** (incluindo a pasta `.github`; no Mac, aperte `Cmd+Shift+.` para ver pastas ocultas) → **Commit changes**.
6. Confira se apareceu `.github/workflows/radar.yml` no repositório. Se não apareceu: **Add file → Create new file**, digite o nome `.github/workflows/radar.yml` e cole o conteúdo do arquivo.

### 3. Colocar as senhas (Secrets)
1. No repositório: **Settings → Secrets and variables → Actions → New repository secret**.
2. Crie estes:

| Name | Valor |
|---|---|
| `TELEGRAM_TOKEN` | token do BotFather |
| `TELEGRAM_CHAT_ID` | número do chat id |
| `SEATS_AERO_KEY` | *(opcional, passo 6)* chave `pro_...` do Seats.aero |

### 4. Ligar o agendamento
1. Aba **Actions** → se aparecer um aviso, clique **I understand my workflows, go ahead and enable them**.
2. Clique em **Radar de Milhas Azul** (à esquerda) → **Run workflow** → **Run workflow**.
3. Em ~1 minuto deve chegar no Telegram: *"Radar de Milhas Azul ativado!"*.
4. A partir daí roda sozinho a cada 3 horas.

### 5. Ligar o painel web
1. **Settings → Pages**.
2. Em *Source*: **Deploy from a branch** · Branch: **main** · pasta **/docs** → **Save**.
3. Em 1–2 minutos aparece o link: `https://SEU-USUARIO.github.io/radar-milhas/`. Salve nos favoritos do celular.

### 6. (Opcional) Monitor de assentos-prêmio
1. Assine o **Pro** em seats.aero.
2. Vá em **seats.aero/settings → aba API → Generate** e copie a chave `pro_...`.
3. Crie o secret `SEATS_AERO_KEY` (passo 3) e rode o workflow de novo (passo 4.2).
4. O histórico/mediana começa a valer depois de ~5 dias de coleta. Até lá, só o teto de preço dispara alerta.

---

## Ajustes (arquivo `config.json`)

Edite direto no GitHub (clique no arquivo → ícone de lápis → *Commit changes*).

| Campo | O que faz | Padrão |
|---|---|---|
| `thresholds_points_one_way` | Teto de pontos (só ida) por região e cabine que dispara alerta | Europa: 55 mil eco / 150 mil exec · EUA: 45 mil / 120 mil · Am. Sul: 8 mil / 40 mil |
| `drop_vs_median_pct` | Quanto abaixo da mediana histórica conta como oportunidade | 25% |
| `destination_regions` | Regiões monitoradas | América do Norte, Europa, América do Sul |
| `realert_after_days` | Não repete o mesmo alerta antes de X dias (a não ser que caia mais) | 7 |
| `feeds` | Blogs lidos | 4 blogs |
| `max_alerts_per_run` | Limite de mensagens por rodada | 8 promoções / 10 rotas |

⚠️ Os tetos padrão são um **ponto de partida chutado**. Depois de 1–2 semanas olhe a aba *Histórico de preços* do painel e ajuste para os valores que você considera bons.

Para mudar a frequência, edite em `.github/workflows/radar.yml` a linha `cron: "17 */3 * * *"` (ex: `"17 */6 * * *"` = a cada 6h).

## Bom saber
- Os preços do Seats.aero vêm de cache (podem ter algumas horas). **Confirme sempre no site/app da Azul antes de transferir pontos.**
- O plano Pro do Seats.aero é para uso pessoal (não comercial), com limite de 1.000 consultas/dia. Este robô usa ~50/dia.
- Se o GitHub pausar o agendamento por inatividade, entre na aba **Actions** e clique em **Enable workflow**.
- Teste local sem internet: `python scripts/teste_offline.py` (mostra as mensagens que iriam para o Telegram).
