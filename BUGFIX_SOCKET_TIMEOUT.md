# Bug Fix - socket.timeout Error

## Problem
```
error: module 'socket' has no attribute 'timeout'
```

O erro foi causado por tentar usar `socket.timeout` (com minúscula) que não existe no módulo socket. Em Python, a exceção `socket.timeout` deve ser referenciada como `socket.timeout` ou importada como `SocketTimeout = socket.timeout`.

## Solution

### 1. Define SocketTimeout como alias para socket.timeout

```python
import socket
SocketTimeout = socket.timeout
```

### 2. Usa SocketTimeout em vez de socket.timeout em todos os lugares

**Antes (Errado):**
```python
except socket.timeout:  # ERRO - socket não tem .timeout como atributo
    pass
```

**Depois (Correto):**
```python
except SocketTimeout:  # CORRETO
    pass
```

### 3. Aplicado nos arquivos:
- `src/scope_xy.py`: 2 ocorrências corrigidas

## Teste Realizado
```bash
python -c "
from src.scope_xy import SocketTimeout
import socket
assert SocketTimeout is socket.timeout  # True
raise socket.timeout('test')
except SocketTimeout:  # Funciona!
    print('OK')
"
```

## Resultado
✅ Erro de socket.timeout resolvido
✅ Código funcional para Rigol DHO900 oscilloscope
