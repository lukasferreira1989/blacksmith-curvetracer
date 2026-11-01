# Blacksmith CurveTracer

[English](README.md) | **Português (Brasil)**

<p align="center">
  <img src="docs/images/blacksmith.jpeg" alt="Logo do Blacksmith CurveTracer" width="240">
</p>

[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![Licença](https://img.shields.io/badge/licen%C3%A7a-MIT-green)](LICENSE)
[![Plataformas](https://img.shields.io/badge/plataformas-Linux%20%7C%20Windows-lightgrey)](#requisitos)

O **Blacksmith CurveTracer** adquire o **display X-Y** de um osciloscópio Rigol
DHO800/DHO900 ou MSO5000, emparelha CH1/CH2 amostra por amostra e plota a curva
V-I no PC. Suporta LAN e USB, capturas de 10k–1M pontos, exportação CSV, cadastro
de componentes em SQLite e comparação referência × captura atual.

> **⚠️ Isto não é um traçador de curvas autônomo.** O software apenas lê a tela
> do osciloscópio. Você precisa de um **testador de curva VI** analógico externo
> — por exemplo o **ASA VI Curve Tester** — conectado aos canais CH1/CH2.

![Blacksmith CurveTracer conectado a um MSO5074](docs/images/gui-mso5074.png)

## Sumário

- [Recursos](#recursos)
- [Hardware necessário](#hardware-necessário)
- [Instalação e execução](#instalação-e-execução)
- [Início rápido](#início-rápido)
- [Usando a GUI](#usando-a-gui)
- [Pipeline de captura e memória](#pipeline-de-captura-e-memória)
- [Escala do display e matemática](#escala-do-display-e-matemática)
- [Formatos de dados](#formatos-de-dados)
- [Cadastro de componentes](#cadastro-de-componentes)
- [Compatibilidade SCPI](#compatibilidade-scpi)
- [Configuração e ambiente](#configuração-e-ambiente)
- [Testes](#testes)
- [Solução de problemas](#solução-de-problemas)
- [Desempenho e limitações](#desempenho-e-limitações)
- [Estrutura do projeto](#estrutura-do-projeto)
- [Desenvolvimento](#desenvolvimento)
- [Segurança, licença e contribuição](#segurança-licença-e-contribuição)
- [Doações](#doações)

---

## Recursos

- **Rigol DHO800/900 e MSO5000** com detecção automática de família.
- **Aquisição X-Y** de CH1/CH2, preservando a ordem original das amostras.
- **Capturas RAW de 10.000 a 1.000.000 de pontos**, ou 1.000 pontos de tela em
  `NORM`.
- **LAN socket, PyVISA e USB-TMC** (PyUSBTMC ou NI-VISA/pyvisa-py).
- **Captura única e tempo real** com intervalo configurável.
- **Grade 8 x 8** com escala, offset e unidades SI do instrumento.
- **Cursor** (`Off`, `Free`, `Single-Plot`) com leitura em unidades físicas.
- **Importação/exportação CSV** e save/load de setup em JSON.
- **Cadastro de componentes** (SQLite): imagens, pinos, capturas e comparação.
- **Executável Windows** com PyInstaller e GitHub Actions.

**Testado:** DHO924S `00.01.04` (LAN) e MSO5074 `00.01.03.03.00` (USB).

---

## Hardware necessário

A cadeia de medição tem três partes:

| Parte | Função | Exemplos |
|---|---|---|
| Testador de curva VI externo | Gera a varredura e as tensões X/Y | **ASA VI Curve Tester** (portátil, 2 canais, 4 frequências), Tektronix 576, qualquer traçador analógico com saídas X/Y |
| Osciloscópio Rigol | Mostra a curva X-Y e é lido pelo software | DHO800/900, MSO5000 |
| PC + este software | Adquire, plota, exporta e compara | Blacksmith CurveTracer |

![Ligação do hardware necessário](docs/images/required-hardware-wiring.png)

1. Conecte as pontas do testador ao dispositivo sob teste (DUT).
2. Saída **X** (ou canal X) do testador → **CH1** do osciloscópio (tensão).
3. Saída **Y** (ou canal Y) do testador → **CH2** (corrente/shunt).
4. Use terra comum entre testador e osciloscópio.
5. Conecte o osciloscópio ao PC via LAN ou USB.

Dependendo do modelo, X/Y podem ser jacks separados ou selecionados por uma
chave. As saídas precisam ser tensões analógicas compatíveis com as entradas do
osciloscópio; um testador sem saídas X/Y não serve para este software.

### Sondas e shunt

- Use **sondas 1x** para melhor precisão; ajuste **Probe X/Y** para 10x.
- Com **Shunt R > 0**, a corrente é `I = V_CH2 / R` e o eixo Y fica em ampères.
- Com **Shunt R = 0**, o eixo Y permanece em volts.
- A caixa **Y is Direct Current** é salva no setup; a conversão numérica é
  controlada pelo **Shunt R**.
- Alterar o shunt não recalcula uma curva já plotada; capture novamente.

### ASA VI Curve Tester

O **ASA VI Curve Tester** é um aparelho portátil de baixo custo com **2 canais
e 4 frequências de teste ajustáveis**. Pesquise online por **"ASA VI Curve
Tester"** ou **"testador de curva VI ASA"**, ou consulte um fornecedor local.

> Fotos de anúncios não foram embutidas porque essas imagens têm direitos
> autorais. Se você tiver um ASA, adicione suas fotos em `docs/images/` e
> referencie nesta seção.

![Exemplo de traçador de curvas (Tektronix 576)](docs/images/curve-tracer-example.jpg)

*Exemplo de traçador de curvas real (Tektronix 576); o ASA é uma alternativa
portátil compacta. Foto: Shelby Jueden, [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/),
via [Wikimedia Commons](https://commons.wikimedia.org/wiki/File:Tek576_CurveTracer_TransistorTest.jpg);
redimensionada para este README. A foto é CC BY-SA 4.0; o restante do projeto é MIT.*

---

## Instalação e execução

### Requisitos

- **Linux** (testado), **Windows 10/11 64 bits** (testado/build suportado).
  macOS deve funcionar, mas não é oficialmente testado.
- **Python 3.11+**. Para o `.exe` Windows, use Python **3.11–3.13 64 bits** do
  [python.org](https://www.python.org/downloads/windows/); não use o alias da
  Microsoft Store.
- Pacotes: `PyVISA`, `PyVISA-py[usb]`, `numpy`, `matplotlib`, `PyQt6`,
  `scipy`, `pyserial`, `psutil`.
- Opcionais: `PyUSBTMC` para USB direto no Linux; `pyinstaller`/`Pillow`/`pytest`
  para o build Windows.

**Drivers USB:** no Windows instale **NI-VISA** (recomendado) *ou* vincule o
osciloscópio ao **WinUSB** com [Zadig](https://zadig.akeo.ie/). No Linux,
adicione uma regra udev se o libusb não abrir o dispositivo. LAN não precisa de
driver VISA.

### Linux (código-fonte)

```bash
git clone <url-do-repositório> curve-tracer-oss
cd curve-tracer-oss
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install PyUSBTMC        # opcional: caminho USB direto
python curvetracer.py
```

Se o acesso USB for negado, crie `/etc/udev/rules.d/99-rigol.rules`:

```udev
SUBSYSTEM=="usb", ATTR{idVendor}=="1ab1", MODE="0666", GROUP="plugdev"
```

Depois `sudo udevadm control --reload-rules && sudo udevadm trigger`.

### Windows

A seção Windows é o **único lugar** para as duas opções: rodar do código-fonte
ou gerar o executável.

#### Opção A — rodar do código-fonte

```bat
py -3 -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python curvetracer.py
```

#### Opção B — gerar o `.exe` com `build_windows.bat`

> **TL;DR:** instale Python 3.11–3.13 64 bits, dê duplo clique em
> **`build_windows.bat`** e use `dist\CurveTracer\CurveTracer.exe`.
> Distribua a **pasta `dist\CurveTracer` inteira**, não apenas o `.exe`.

```bat
cd /d E:\caminho\curve-tracer-oss
build_windows.bat
```

Também é possível dar duplo clique em `build_windows.bat`. Se a janela fechar
imediatamente, rode pelo `cmd.exe` para ver o erro.

O script:

1. localiza um Python 64 bits suportado;
2. cria/usa `.venv-win`;
3. instala `requirements.txt` e `requirements-build.txt`;
4. roda os testes automatizados com descoberta desativada;
5. gera `docs\images\blacksmith.ico` a partir de `docs\images\blacksmith.jpeg`;
6. gera com `python -m PyInstaller --noconfirm --clean CurveTracer.spec`;
7. executa `dist\CurveTracer\CurveTracer.exe --self-check`;
8. verifica se o executável existe.

Resultado:

```text
dist\CurveTracer\CurveTracer.exe
```

A pasta contém o executável **e** o runtime Python, Qt, NumPy, SciPy,
Matplotlib e as bibliotecas USB. Zipe e distribua a pasta inteira.

> **Importante:** o PyInstaller não é um cross-compiler. Um `.exe` Windows deve
> ser gerado no Windows (ou runner Windows); build no Linux/WSL gera um binário
> Linux.

**Build manual (somente para depuração):**

```bat
py -3.12 -m venv .venv-win
.venv-win\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt -r requirements-build.txt
python -m unittest discover -s tests
python -m PyInstaller --noconfirm --clean CurveTracer.spec
dist\CurveTracer\CurveTracer.exe --self-check
```

**Rodar/testar o executável:**

```bat
dist\CurveTracer\CurveTracer.exe
tools\windows\test_exe.bat
tools\windows\test_run.bat
```

O ícone vem de `docs/images/blacksmith.jpeg` via `tools/make_icon.py`; a mesma
imagem é usada como ícone da janela. Logs do build sem console:
`%LOCALAPPDATA%\CurveTracer\curvetracer.log`.

**GitHub Actions:** o workflow
[`.github/workflows/build-windows.yml`](.github/workflows/build-windows.yml)
compila em `windows-latest` e publica o artefato `CurveTracer-windows`.

### macOS (código-fonte, experimental)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python curvetracer.py
```

Use PyVISA/NI-VISA ou pyvisa-py para conectar ao instrumento.

---

## Início rápido

1. Monte o testador VI externo e ligue-o a CH1/CH2 (veja
   [Hardware necessário](#hardware-necessário)).
2. Conecte o osciloscópio ao PC via LAN ou USB.
3. Execute `python curvetracer.py`.
4. Clique em **Refresh**, selecione o osciloscópio e clique em **CONNECT**.
5. Configure CH X/Y, sondas e shunt; clique em **CAPTURE**.
6. Use **SAVE Data** para CSV ou **COMPONENTS** para salvar uma referência.

---

## Usando a GUI

A janela principal está no topo deste README.

### Barra superior

| Controle | Descrição |
|---|---|
| **SAVE Setup / LOAD Setup** | Salva/carrega configuração JSON. |
| **Resource** | Combo editável com dispositivos descobertos; digite um resource VISA/socket se necessário. |
| **Refresh** | Reexecuta a descoberta USB/LAN. |
| **CONNECT** | Conecta/desconecta. |
| **CAPTURE** | Captura única ou inicia/para o tempo real. |
| **COMPONENTS** | Abre o cadastro de componentes. |

### Configuração do osciloscópio

| Ajuste | Padrão | Descrição |
|---|---|---|
| CH X (Voltage) | `CHAN1` | Canal do eixo X. |
| CH Y (Current) | `CHAN2` | Canal do eixo Y. |
| Probe X / Y | `1.0` | Atenuação da sonda (`0.001`–`10000`). |
| Y is Direct Current | marcado | Salvo no setup; veja a observação do shunt. |
| Shunt R (Ω) | `0` | `I = V/R` quando > 0; `0` mantém Y em volts. |
| Invert Y | desmarcado | Inverte o sinal de Y. |

> No MSO5000 as fontes X/Y são fixas em CH1/CH2. No DHO800/900 os seletores
> são aplicados com `:TIMebase:XY:X/Y`.

### Configurações de aquisição

| Ajuste | Padrão | Descrição |
|---|---|---|
| Update Mode | `Single Capture` | `Single Capture` ou `Real-time`. |
| Update Rate | `5.0 s` | Intervalo entre frames (`0.1`–`10.0 s`). |
| Mem Depth | `Auto` | `Auto`, `1k`, `10k`, `100k`, `1M`, `5M`/`10M` (DHO) ou `10M`–`200M` (MSO). Valores ≤ 1M são lidos em RAW; Auto/maiores usam 1.000 pontos da tela. |
| Update | `N/A` | Taxa efetiva do tempo real. |

### Modos de captura

- **Single Capture:** clique em **CAPTURE**; a aquisição roda em thread de
  trabalho, o osciloscópio para só para ler o frame e retoma em X-Y.
- **Real-time:** selecione `Real-time`, ajuste o intervalo e clique em
  **CAPTURE**; o botão vira **STOP Real-time**.

### Gráfico e cursor

- **Grid** mostra/oculta a grade.
- **Cursor**: `Off`, `Free` (segue o mouse) ou `Single-Plot` (clique para
  posicionar/mover). Os valores incluem a conversão por shunt.
- **SAVE Data / LOAD Data / PRINT Screen**: CSV e PNG/JPG.

### Estados de exibição

| Estado | O que aparece |
|---|---|
| Aberto, sem conexão | Dica central “No data”. |
| Conectado, sem captura | Grade 8 x 8 vazia na escala/offset do osciloscópio. |
| Após captura / LOAD Data | Grade + curva na escala do instrumento. |

---

## Pipeline de captura e memória

Para cada captura:

1. Identifica o instrumento com `*IDN?` e escolhe o dialeto DHO/MSO.
2. Garante X-Y: DHO `:TIMebase:XY:ENABle ON`; MSO `:TIMebase:MODE XY`.
3. Sincroniza fontes X/Y (DHO `:TIMebase:XY:X/Y`; MSO fixo CH1/CH2).
4. Para a aquisição para ler os dois canais do mesmo frame.
5. Verifica o display dos canais com `:CHANnel<n>:DISPlay?`; evita reescrever
   `DISP ON`.
6. Configura `:WAVeform:SOURce/MODE/FORMat` e `:STARt`/`:STOP`; lê o preâmbulo.
7. Lê `:WAVeform:DATA?`, interpreta o bloco TMC e converte com
   `V = (raw - YREFerence - YORigin) * YINCrement`.
8. Emparelha os canais por índice, aplica sonda/shunt/inversão e retoma a
   aquisição.

### Profundidade de memória e pontos

O seletor **Mem Depth** escreve `:ACQuire:MDEPth` (padrão **Auto**):

| Profundidade selecionada | Modo | Pontos por canal |
|---|---|---|
| `Auto` com profundidade ≤ 1M | `RAW` | profundidade atual |
| `Auto` com profundidade > 1M | `NORM` | 1.000 pontos da tela |
| `1k`, `10k`, `100k`, `1M` | `RAW` | exatamente a profundidade escolhida |
| `5M`…`200M` | `NORM` | 1.000 pontos da tela |

`WAVEFORM_MAX_POINTS = 1_000_000` é um limite de segurança para
transferência/plotagem, não do instrumento. A profundidade escolhida permanece
na sessão; ao desconectar o driver restaura `Auto`. O MSO pode dividir blocos
RAW grandes em transferências USBTMC de ~200 KB; o driver as junta.

---

## Escala do display e matemática

As duas famílias usam uma **grade X-Y quadrada de 8 x 8**:

```text
span   = 8 * Volts_por_divisão
centro = -offset
min    = centro - span/2
max    = centro + span/2
```

Isso segue `V = (raw - YREFerence - YORigin) * YINCrement`; no centro da tela
`V = -offset`. A GUI usa a mesma convenção. A conversão por shunt também divide
a escala/centro de Y por `R`; as sondas multiplicam os dados do canal.

| Tela X-Y do instrumento | GUI |
|---|---|
| ![Tela X-Y do MSO5074](docs/images/mso5074-xy-screen.png) | ![Curva na GUI](docs/images/gui-curve-example.png) |

Nenhuma normalização entre eixos é aplicada: os pares originais são
preservados, uma linha vertical continua vertical e elipses mantêm a forma.

---

## Formatos de dados

**CSV** (`SAVE Data`/`LOAD Data`):

```csv
Voltage_V,Current_A
-1.234,0.000123
```

As amostras são gravadas na ordem de aquisição. `LOAD Data` aceita
`Voltage_V`/`Current_A`, `V`/`I` ou `X`/`Y`, e arquivos de duas colunas sem
header. Com `Shunt R = 0`, a segunda coluna é a tensão do eixo Y; o header
continua `Current_A`.

**Setup JSON:** chaves `resource`, `ch_x`, `ch_y`, `probe_x`, `probe_y`,
`y_direct`, `shunt`, `invert`, `update_mode`, `update_rate`, `mem_depth`.
Ao carregar, o resource salvo é adicionado à combo se necessário.

---

## Cadastro de componentes

Abra com **COMPONENTS**. É uma janela separada, não modal, com três abas.

![Cadastro de componentes](docs/images/component-registry.png)

- **Profile & Pins:** imagem de referência, metadados, tabela de pinos e
  posições normalizadas na imagem (`0..1`).
- **Captures:** **CAPTURE Now + SAVE**, **SAVE Current Capture**, **IMPORT
  CSV**. Cada amostra é salva na ordem de aquisição com unidades e label.
- **Compare:** selecione uma referência, clique em **USE Current Capture** (ou
  **CAPTURE + COMPARE**) e em **COMPARE**.

A comparação mostra método, número de amostras, RMS/NRMSE, desvio máximo/P95,
correlação e veredito:

| Veredito | Critério (tolerância padrão 5% do span Y da referência) |
|---|---|
| **MATCH** | NRMSE ≤ tolerância, desvio máximo ≤ 2× tolerância, correlação ≥ 0,90 |
| **WARNING** | NRMSE ≤ 2× tolerância e desvio máximo ≤ 4× tolerância |
| **DEVIATION** | além dos limites de warning |

Curvas monotônicas usam interpolação; laços usam vizinho mais próximo
geométrico. As amostras salvas nunca são ordenadas, suavizadas ou modificadas;
as unidades precisam coincidir.

![Comparação referência × captura atual](docs/images/component-compare.png)

Banco: `~/.curvetracer/components.db`; override com `CURVETRACER_DB`. Imagens
em BLOB, capturas em arrays JSON. Excluir um componente remove pinos/capturas;
excluir um pino mantém as capturas.

---

## Compatibilidade SCPI

| Comando | DHO800/900 | MSO5000 | Observações |
|---|---|---|---|
| `*IDN?` | ✅ | ✅ | Detecção de família |
| `:RUN` / `:STOP` / `:SING` | ✅ | ✅ | Aquisição |
| `:TIMebase:MODE XY` | ✅ | ✅ | X-Y no MSO; válido no DHO |
| `:TIMebase:MODE?` | ✅ | ✅ | DHO retorna MAIN/ROLL; MSO retorna XY |
| `:TIMebase:XY:ENABle` | ✅ | ❌ | Habilitação X-Y do DHO |
| `:TIMebase:XY:X/Y` | ✅ | ❌ | Fontes X/Y do DHO |
| `:CHANnel<n>:SCALe?` / `:OFFSet?` | ✅ | ✅ | Escala/offset |
| `:CHANnel<n>:DISPlay?` | ✅ | ✅ | Estado do canal |
| `:WAVeform:SOURce/MODE/FORMat` | ✅ | ✅ | Configuração da waveform |
| `:WAVeform:STARt/STOP` | ✅ | ✅ | Faixa RAW |
| `:WAVeform:PREamble?` / `:DATA?` | ✅ | ✅ | Preâmbulo/dados TMC |
| `:ACQuire:MDEPth?` | ✅ | ✅ | Seleção de Mem Depth |
| `:ACQuire:SRATe?` | ✅ | ✅ | Taxa de amostragem |
| `:SYSTem:ERRor?` | ✅ | ✅ | Error queue |

PDFs de referência em [`docs/`](docs/): guia DHO800/900 e guia MSO5000.

---

## Configuração e ambiente

| Variável | Efeito |
|---|---|
| `CURVETRACER_DB` | Caminho do banco SQLite de componentes. |
| `CURVETRACER_SKIP_DISCOVERY` | Pula a descoberta USB/LAN na GUI. |
| `CURVETRACER_NO_DISCOVERY` | Alias da anterior. |
| `QT_QPA_PLATFORM` | `offscreen` para testes headless; no Linux o padrão é `xcb`. |
| `LOCALAPPDATA` | Pasta de logs do app congelado no Windows. |

Testes headless:

```bash
QT_QPA_PLATFORM=offscreen \
CURVETRACER_SKIP_DISCOVERY=1 \
CURVETRACER_NO_DISCOVERY=1 \
python -m pytest tests -q
```

---

## Testes

```bash
python -m pytest tests -q
python -m unittest discover -s tests
```

**131 testes** passam no Linux. No Windows sem `PyUSBTMC`, dois testes de
hardware são pulados (129 passando, 2 pulados). O `pytest.ini` restringe a
coleta a `tests/`; scripts manuais ficam em `tools/diagnostics/` e não são
executados pela CI nem pelo `build_windows.bat`.

Principais arquivos: `test_scope_commands.py`, `test_iv_reconstruction.py`,
`test_gui_states.py`, `test_mso_compat.py`, `test_component_db.py`,
`test_component_compare.py`, `test_component_gui.py`, `test_curvetracer.py`.

Validado em hardware real: DHO924S (LAN) e MSO5074 (USB), incluindo capturas
RAW de 10k/100k/1M e Auto/NORM.

---

## Solução de problemas

- **Não descobre:** verifique LAN/sub-rede/firewall porta 5555; no USB clique em
  **Refresh** e confira `lsusb`/udev (Linux) ou NI-VISA/WinUSB (Windows). A
  descoberta varre até 1022 hosts; digitar o resource direto funciona.
- **Timeout USB no MSO:** o driver usa init USBTMC “lite” sem
  `GET_CAPABILITIES`; se ainda falhar, desligue/ligue o osciloscópio com o cabo
  conectado, reconecte ou use LAN.
- **Só um pequeno arco / curva errada:** use **Mem Depth Auto** (pontos da tela)
  ou uma profundidade explícita ≤ 1M; confira CH1=X/CH2=Y, sondas, shunt e
  **Invert Y**.
- **Sem dados:** confirme canais exibidos e modo X-Y; confira `:SYST:ERR?` no
  log.
- **Save/load de setup:** o campo Resource é editável; ao carregar, o resource
  salvo é adicionado à lista.
- **Logs no Windows:** `%LOCALAPPDATA%\CurveTracer\curvetracer.log`.

---

## Desempenho e limitações

| Operação | DHO924S (LAN) | MSO5074 (USB) |
|---|---|---|
| Conexão + IDN | ~1 s | ~0,6–1,3 s |
| Auto (NORM 1.000 pts no MSO) | ~2 s | ~2 s |
| 10k RAW | ~2 s | ~2 s |
| 1M RAW | — | ~2,5 s de captura (~4 s com plotagem) |

- **Fontes X-Y do MSO são fixas em CH1/CH2.**
- **A profundidade de memória é escolhida pelo usuário** (padrão Auto); ao
  desconectar, Auto é restaurado. Se o app for morto, confira o menu Mem Depth.
- **Limite de 1M pontos RAW** é de transferência/plotagem; profundidades
  maiores usam NORM.
- **Grade 8 x 8** nas duas famílias.
- **Y is Direct Current** é salvo, mas a conversão usa **Shunt R**.
- **Header do CSV** é fixo; sem shunt a segunda coluna é tensão.
- `src/driver.py` e `src/discovery.py` são auxiliares/legados; a GUI usa
  `src/scope_xy.py`.
- macOS não é oficialmente testado; o `.exe` Windows deve ser gerado no Windows.
- Firmware validado em DHO924S `00.01.04` e MSO5074 `00.01.03.03.00`.

---

## Estrutura do projeto

```text
curve-tracer-oss/
├── curvetracer.py              # entry point + --self-check
├── CurveTracer.spec            # build PyInstaller
├── build_windows.bat           # build do .exe Windows
├── pytest.ini                  # coleta apenas tests/
├── requirements*.txt
├── LICENSE / README*.md / CHANGELOG.md
├── docs/
│   ├── BUILD_WINDOWS.md, USAGE.md, RIGOL_XY.md, ROADMAP.md
│   ├── DHO800900_ProgrammingGuide_EN.pdf, MSO5_programming_guide.pdf
│   ├── images/                 # screenshots + atribuições
│   └── internal/               # notas históricas de refatoração
├── examples/
│   ├── rigol_xy_capture.py
│   └── data/                   # curvas CSV de exemplo
├── src/
│   ├── scope_xy.py             # transporte + SCPI + captura X-Y
│   ├── gui.py                  # janela principal PyQt6
│   ├── component_db.py, component_compare.py, component_gui.py
│   ├── driver.py, discovery.py, curve_reconstruct.py, simulator.py
├── tools/
│   ├── make_icon.py, compatibility_matrix.py, install-ni-visa.sh
│   ├── diagnostics/            # scripts manuais (fora da CI)
│   └── windows/                # helpers para testar o executável
└── tests/                      # 131 testes automatizados
```

---

## Desenvolvimento

- Rode do código-fonte: `python curvetracer.py` ou `python src/gui.py`.
- Adicione recursos SCPI em `src/scope_xy.py`; confira os dois PDFs e use
  `_is_mso_family()` para comandos específicos.
- Adicione testes em `tests/` (sem hardware); use `tools/diagnostics/` apenas
  para sondagens manuais.
- Mantenha I/O do instrumento em threads de trabalho; nunca ordene, suavize ou
  reescreva amostras adquiridas.
- Valide em hardware real quando alterar comportamento SCPI.

---

## Segurança, licença e contribuição

**Segurança:** comece com tensões/correntes baixas, use limite de corrente,
respeite os limites de sondas/osciloscópio/DUT, use aterramento/isolamento
adequados e nunca exceda os limites do dispositivo. Os autores não se
responsabilizam por danos ou ferimentos.

**Licença:** MIT — veja [LICENSE](LICENSE).

**Contribuição:** faça fork, crie uma branch, adicione testes, rode a suíte,
valide em hardware quando relevante e envie um PR. Relatos de bug devem incluir
`*IDN?`, método de conexão, SO/versão do Python, texto do erro e passos para
reproduzir.

**Agradecimentos:** Rigol pelos guias e instrumentos; às comunidades PyVISA,
PyUSBTMC, PyQt6, Matplotlib, NumPy e SciPy; e aos contribuidores originais do
CurveTracer OSS.

---

## Doações

Se este projeto te ajudou:

**Bitcoin (BTC):**

```text
bc1q2p5mpsulcger8af3fp2e2rj4hehtmul5zt5fsr
```

Sem obrigação — contribuições de código, relatos de bug e feedback de hardware
são igualmente valiosos.

---

Veja [CHANGELOG.md](CHANGELOG.md) para o histórico (atual: **2.1.0**).
Guias detalhados: [docs/USAGE.md](docs/USAGE.md),
[docs/BUILD_WINDOWS.md](docs/BUILD_WINDOWS.md),
[docs/RIGOL_XY.md](docs/RIGOL_XY.md).
