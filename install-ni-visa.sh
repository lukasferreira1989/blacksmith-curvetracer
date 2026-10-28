#!/bin/bash
# Script para instalar NI-VISA no Ubuntu 26.04

set -e

echo "=== Instalando NI-VISA para Rigol DHO ==="
echo

# Passo 1: Copiar chave GPG
echo "Passo 1: Copiando chave GPG..."
sudo cp /tmp/ni-extract/usr/share/keyrings/ni-software-2026-noble.asc /usr/share/keyrings/
echo "Chave GPG copiada com sucesso"
echo

# Passo 2: Adicionar repositório
echo "Passo 2: Adicionando repositório NI..."
sudo cp /tmp/ni-extract/etc/apt/sources.list.d/ni-software-2026-noble.list /etc/apt/sources.list.d/
echo "Repositório NI adicionado com sucesso"
echo

# Passo 3: Atualizar lista de pacotes
echo "Passo 3: Atualizando lista de pacotes..."
sudo apt-get update
echo "Apt update concluído"
echo

# Passo 4: Instalar NI-VISA
echo "Passo 4: Instalando NI-VISA..."
sudo apt-get install -y ni-visa
echo "NI-VISA instalado com sucesso"
echo

# Passo 5: Verificar instalação
echo "Passo 5: Verificando instalação..."
visa list 2>&1 || echo "Verifique manualmente com: visa list"
echo

echo "=== Instalação concluída ==="
echo
echo "Para usar o NI-VISA com Python:"
echo "  import pyvisa"
echo "  rm = pyvisa.ResourceManager('@ni')"
echo "  print(rm.list_resources())"
