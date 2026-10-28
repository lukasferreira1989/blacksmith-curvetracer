# Guia de Instalação do NI-VISA para Rigol DHO

## O que fazer

Execute os comandos abaixo no terminal (um por um):

```bash
# Passo 1: Copiar chave GPG
sudo cp /tmp/ni-extract/usr/share/keyrings/ni-software-2026-noble.asc /usr/share/keyrings/

# Passo 2: Adicionar repositório NI
sudo cp /tmp/ni-extract/etc/apt/sources.list.d/ni-software-2026-noble.list /etc/apt/sources.list.d/

# Passo 3: Atualizar lista de pacotes
sudo apt-get update

# Passo 4: Instalar NI-VISA
sudo apt-get install -y ni-visa

# Passo 5: Verificar instalação
visa list
```

## Verificar no Python

Depois da instalação, teste no Python:

```python
import pyvisa
rm = pyvisa.ResourceManager('@ni')  # Use o backend NI-VISA
resources = rm.list_resources()
print(resources)
```

Você deve ver algo como:
```
('USB0::0x1AB1::0x044C::DHO924S000001::INSTR',)
```

## Usar no Curve Tracer

Após instalar o NI-VISA:

1. Reconecte o USB do osciloscópio
2. Abra o Curve Tracer
3. Clique em **REFRESH** na lista de recursos
4. Ou deixe o campo vazio e clique em **CONNECT** para auto-detect

## Solução de Problemas

### Erro: "Não é possível acessar /usr/share/keyrings"

Certifique-se de usar `sudo` nos comandos.

### Erro: "Package ni-visa not found"

Execute `sudo apt-get update` novamente para atualizar a lista de pacotes.

### Erro: "Permission denied" ao acessar USB

Adicione seu usuário ao grupo `plugdev`:
```bash
sudo usermod -a -G plugdev $USER
```

Reinicie a sessão ou execute:
```bash
sudo udevadm control --reload-rules
sudo udevadm trigger
```

### Dispositivo não aparece

1. Verifique se o osciloscópio está ligado
2. Verifique se o cabo USB está conectado firmemente
3. Execute `lsusb | grep Rigol` para confirmar o dispositivo
4. Tente outro porto USB

## Comando para verificar o dispositivo USB

```bash
lsusb | grep Rigol
```

Saída esperada:
```
Bus 001 Device 014: ID 1ab1:044c Rigol Technologies DHO924S
```

## Comando para verificar recursos VISA

```bash
visa list
```

Saída esperada:
```
USB0::0x1AB1::0x044C::DHO924S000001::INSTR
```
