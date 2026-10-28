# Instalação do NI-VISA para Linux

## O que é NI-VISA?

NI-VISA é uma biblioteca da National Instruments que fornece uma interface unificada para controlar instrumentos de medição, incluindo dispositivos USB-TMC como o **Rigol DHO800/DHO900**.

## Por que instalar?

- **PyVISA-py (`@py`) não suporta USB-TMC** - é uma limitação conhecida
- NI-VISA **suporta USB-TMC e TCP/IP** - permite conexão direta via USB
- O Rigol DHO conecta via **USBTest** (LXI over USB) que é compatível com USB-TMC

## Requisitos

- Sistema Linux (Ubuntu, Debian, Fedora, etc.)
- Usuário com permissões de sudo
- Conexão USB entre o computador e o osciloscópio

## Instalação

### 1. Baixar o instalador

Visite o site da National Instruments:
- https://www.ni.com/en/support/download/download.ni-visa.html

Ou use o link direto para Linux:
- https://www.ni.com/de-de/support/downloads/drivers/download.ni-visa.html

Baixe o arquivo `.run` (ex: `ni-visa-2023q4-linux-installer.run`)

### 2. Tornar o instalador executável

```bash
chmod +x ni-visa-<versão>-linux-installer.run
```

### 3. Executar o instalador

```bash
sudo ./ni-visa-<versão>-linux-installer.run
```

Siga as instruções na tela. Aceite a licença e escolha a instalação completa.

### 4. Verificar a instalação

```bash
visa list
```

Ou use Python:

```python
import pyvisa
rm = pyvisa.ResourceManager('@ni')
print(rm.list_resources())
```

Você deve ver algo como:
```
('USB0::0x1AB1::0x044C::DHO924S000001::INSTR',)
```

### 5. Configurar permissões USB (se necessário)

Se o dispositivo não for detectado, adicione seu usuário ao grupo `plugdev`:

```bash
sudo usermod -a -G plugdev $USER
```

Reinicie a sessão ou execute:

```bash
sudo udevadm control --reload-rules
sudo udevadm trigger
```

## Usar com o Curve Tracer

Após instalar o NI-VISA, reconecte o USB do osciloscópio e no campo "VISA Resource" da GUI:

1. Clique em **REFRESH** para atualizar a lista de recursos
2. Ou deixe o campo vazio e clique em **CONNECT** para auto-detect
3. O dispositivo USB-TMC será detectado automaticamente

O recurso deverá ser algo como:
```
USB0::0x1AB1::0x044C::DHO924S000001::INSTR
```

## Resolução de Problemas

### Erro: "Wrapper not found: No package named pyvisa_ni"

Isso significa que o NI-VISA não está instalado corretamente. Reinstale seguindo os passos acima.

### Erro: "Permission denied" ao acessar USB

Adicione seu usuário ao grupo `plugdev` (ver passo 5 acima) ou use:

```bash
sudo chmod 666 /dev/usbtmc*
```

### Dispositivo não aparece na lista

1. Verifique se o osciloscópio está ligado
2. Verifique se o cabo USB está conectado firmemente
3. Execute `lsusb | grep Rigol` para confirmar o dispositivo
4. Tente outro porto USB
5. Reinicie o computador

## Alternativa: Conexão TCP/IP

Se não quiser instalar o NI-VISA, pode conectar o osciloscópio via Ethernet:

1. Configure o IP no osciloscópio (Menu: System → Network)
2. Use o recurso: `TCPIP::<IP>::INSTR`
3. Exemplo: `TCPIP::192.168.1.100::INSTR`

O PyVISA-py suporta TCP/IP nativamente, sem necessidade de NI-VISA.
