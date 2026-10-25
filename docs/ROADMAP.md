# Projeto: evolução completa do CurveTracer OSS para o Rigol DHO924S

## Objetivo geral

Inspecione o repositório existente do CurveTracer OSS e amplie suas funcionalidades para aproveitar, de forma integrada, os recursos documentados do osciloscópio Rigol DHO924S, transformando o software em uma plataforma completa de caracterização elétrica, diagnóstico e análise de componentes eletrônicos. Deixei o osciloscópio ligado na rede e na usb para você validar as coisas, mas o ip e a porta usb podem mudar.

**Execute o trabalho diretamente no código existente.** Não se limite a apresentar um plano, uma análise ou sugestões. Inspecione os arquivos, implemente as alterações necessárias, execute os testes disponíveis, corrija os problemas encontrados e apresente um resumo das modificações realizadas.

## 1. Inspeção inicial e documentação do instrumento

1. Leia integralmente os trechos relevantes do manual de programação `docs/DHO800900_ProgrammingGuide_EN.pdf`.
2. Identifique as capacidades reais do modelo e as diferenças entre funcionalidades padrão, opcionais e indisponíveis.
3. Inspecione a arquitetura do CurveTracer OSS, identificando:
   - Driver de comunicação com o osciloscópio.
   - Implementação de comandos SCPI.
   - Configuração de canais e escalas.
   - Aquisição e transferência de formas de onda.
   - Processamento de dados.
   - Reconstrução das curvas I–V.
   - Interface gráfica e atualização dos gráficos.
   - Exportação de dados e relatórios.
   - Tratamento de erros e testes existentes.
4. Identifique controles da interface que não executam nenhuma ação, opções incompatíveis com o instrumento e funcionalidades parcialmente implementadas.
5. Crie ou atualize uma matriz de compatibilidade entre os recursos do DHO924S, os comandos SCPI documentados e as funcionalidades efetivamente implementadas.
6. Não presuma que comandos de outros modelos Rigol funcionem no DHO924S. Confirme cada comando na documentação pertinente.

## 2. Comunicação e controle do osciloscópio

Implemente ou aprimore o controle remoto por USB e LAN, conforme as interfaces suportadas pelo instrumento.

Funcionalidades desejadas:

- Descoberta e seleção do instrumento.
- Identificação automática por fabricante, modelo e versão de firmware.
- Verificação de conectividade.
- Configuração de endereço e interface de comunicação.
- Conexão, desconexão e reconexão segura.
- Consulta de identificação e estado do instrumento.
- Leitura da fila de erros SCPI.
- Registro de comandos enviados, respostas e falhas.
- Timeouts configuráveis.
- Cancelamento de operações demoradas.
- Recuperação de falhas de comunicação.
- Verificação das configurações efetivamente aplicadas.
- Sincronização entre o estado do software e o estado do osciloscópio.
- Prevenção de comandos simultâneos conflitantes.
- Indicadores de conexão, aquisição, processamento e erro.
- Diagnóstico de problemas de comunicação.
- Teste de conexão sem iniciar uma medição.

Centralize a comunicação em um driver reutilizável. Não espalhe comandos SCPI diretamente pelos componentes da interface gráfica.

## 3. Aquisição de formas de onda

Implemente um mecanismo robusto para adquirir amostras dos canais analógicos.

- Seleção dos canais utilizados.
- Aquisição sincronizada de tensão e corrente.
- Leitura dos dados brutos da forma de onda.
- Interpretação correta dos formatos binários e textuais suportados.
- Tratamento de cabeçalhos, preâmbulos, escalas e offsets.
- Conversão correta dos códigos digitais para unidades físicas.
- Preservação da ordem original das amostras.
- Preservação da correspondência temporal entre canais.
- Leitura da frequência de amostragem efetiva.
- Identificação do número de pontos adquiridos.
- Configuração de memória e profundidade de aquisição dentro dos limites suportados.
- Seleção de aquisição normal, média, peak detect ou outros modos documentados.
- Aquisição única, contínua e acionada por trigger.
- Configuração de trigger por borda, nível, fonte e outros tipos suportados.
- Controle de pré-trigger e pós-trigger quando disponível.
- Detecção de aquisição incompleta.
- Detecção de dados inválidos, saturação e clipping.
- Separação entre aquisição, processamento e renderização gráfica.
- Cache de dados para evitar transferências desnecessárias.
- Atualização da curva sem bloquear a interface.
- Medição pontual e aquisição de alta resolução quando suportadas.

A taxa máxima de amostragem anunciada pelo fabricante não deve ser tratada como garantia de taxa equivalente de atualização da interface.

## 4. Reconstrução correta das curvas I–V

Esta é uma funcionalidade prioritária.

Implemente um mecanismo de reconstrução de curvas que preserve a integridade física e temporal das amostras.

- Manter cada par de tensão e corrente associado à mesma amostra.
- Preservar a sequência original de aquisição.
- Identificar os ciclos de varredura e seus sentidos.
- Separar os ramos de ida e volta quando necessário.
- Reconhecer varreduras periódicas e sinais alternados.
- Tratar corretamente o cruzamento por zero.
- Evitar linhas verticais artificiais, saltos e conexões entre ciclos diferentes.
- Evitar o fechamento artificial de curvas.
- Não ordenar os pontos por tensão ou corrente.
- Não remover pontos apenas porque parecem formar uma descontinuidade.
- Não descartar amostras legítimas para produzir uma curva visualmente mais bonita.
- Detectar descontinuidades por critérios temporais e de aquisição verificáveis.
- Permitir visualizar a curva completa e cada ramo separadamente.
- Diferenciar os sentidos de varredura por cor, legenda ou setas.
- Preservar a relação entre os canais quando a curva é reconstruída.
- Tratar buffers incompletos e aquisições interrompidas.
- Permitir inspeção das amostras que originaram qualquer trecho do gráfico.

Implemente testes automatizados com sinais sintéticos conhecidos, incluindo círculos, elipses, rampas triangulares, ondas senoidais, curvas de diodos e sinais com ruído.

Para o teste de capacitores, valide especificamente que uma aquisição correspondente a uma curva circular ou elíptica não seja transformada em uma linha que sobe e desce ou em um gráfico com linhas verticais internas.

## 5. Sistema de visualização e análise gráfica

Desenvolva uma interface de visualização adequada a medições de bancada.

- Gráficos X–Y com tensão e corrente.
- Gráficos temporais dos canais adquiridos.
- Visualização simultânea de forma de onda e curva I–V.
- Zoom, pan e ajuste automático de escala.
- Escalas lineares e logarítmicas quando matematicamente válidas.
- Cursor horizontal e vertical.
- Leitura de coordenadas e valores numéricos.
- Medição de diferenças entre pontos.
- Seleção de regiões de interesse.
- Marcadores de eventos e pontos característicos.
- Legendas e unidades físicas.
- Grades configuráveis.
- Paletas e estilos de visualização.
- Sobreposição de curvas.
- Comparação entre aquisições.
- Congelamento de uma curva de referência.
- Histórico de curvas.
- Exibição de dados brutos e processados.
- Indicação de saturação, pontos inválidos e regiões de baixa confiabilidade.
- Exportação do gráfico sem alterar os dados originais.
- Interface responsiva durante aquisições contínuas.

A renderização deve ser independente da aquisição. Qualquer redução de pontos usada exclusivamente para desenhar gráficos deve preservar os dados completos para análise e exportação.

## 6. Configuração de circuitos de teste

Crie perfis de teste que relacionem o instrumento, os circuitos externos e o componente sob análise.

- Configuração dos canais de tensão.
- Configuração dos canais usados para medir corrente.
- Definição do resistor shunt e sua tolerância.
- Conversão de tensão no shunt em corrente.
- Compensação de offset e calibração.
- Definição de polaridade.
- Configuração de amplitude, frequência e offset do sinal de excitação.
- Configuração de níveis de polarização.
- Configuração de limites de tensão, corrente e potência.
- Definição de intervalos de varredura.
- Definição de quantidade de ciclos.
- Definição de tempos de estabilização.
- Registro dos componentes externos utilizados.
- Registro das limitações do circuito de teste.

O software deve distinguir claramente as capacidades do osciloscópio das capacidades do circuito externo. O AFG, quando disponível, não deve ser tratado como fonte de potência ou fonte de corrente programável sem que exista um estágio externo adequado.

## 7. Caracterização de diodos

Crie um perfil específico para diodos convencionais, Schottky, LEDs e Zeners, dentro dos limites do circuito utilizado.

- Curva direta e reversa.
- Tensão de condução para correntes selecionadas.
- Corrente de fuga.
- Inclinação local da curva.
- Resistência diferencial.
- Comparação entre componentes.
- Identificação de circuito aberto e curto.
- Estimativa de tensão de ruptura quando o circuito de teste for apropriado.
- Registro da corrente e tensão máximas utilizadas.
- Comparação com faixas de referência configuráveis.

Não declare um componente defeituoso apenas com base em uma curva visualmente diferente. Apresente os parâmetros que fundamentam a classificação.

## 8. Caracterização de transistores BJT

Implemente curvas de saída e análises para transistores NPN e PNP.

- Curvas de corrente de coletor versus tensão coletor-emissor.
- Varredura com diferentes correntes de base.
- Regiões de corte, ativa e saturação.
- Estimativa de ganho de corrente em condições especificadas.
- Corrente de fuga.
- Tensão de saturação.
- Resistência diferencial em regiões selecionadas.
- Comparação entre transistores equivalentes.
- Identificação de junções abertas e curto-circuitadas.
- Registro das condições de polarização.
- Exportação das famílias de curvas.

O software deve permitir definir as correntes e tensões utilizadas, respeitando os limites elétricos do componente.

## 9. Caracterização de MOSFETs e IGBTs

Implemente perfis para transistores de potência, considerando os requisitos específicos de acionamento e proteção.

- Curvas de saída \(I_D \times V_{DS}\) para MOSFETs.
- Curvas de coletor para IGBTs.
- Famílias de curvas para diferentes tensões de gate.
- Estimativa da tensão de limiar.
- Estimativa de resistência de condução em condições definidas.
- Medição de corrente de fuga.
- Caracterização do diodo interno de MOSFETs.
- Comparação entre componentes.
- Identificação de curtos e circuitos abertos.
- Registro da tensão de gate, corrente e temperatura, quando medida.
- Verificação dos limites máximos especificados pelo fabricante.

Diferencie estimativas obtidas por varredura de medições padronizadas de datasheet. A tensão de limiar não deve ser confundida com a tensão necessária para obter baixa resistência de condução.

## 10. Capacitores e componentes passivos

Implemente recursos para caracterização de capacitores, resistores, indutores e outros componentes passivos.

### Capacitores

- Curvas I–V.
- Visualização dos ramos de carga e descarga.
- Identificação de laços e histerese.
- Estimativa de capacitância a partir de corrente e derivada da tensão, quando aplicável.
- Comparação entre capacitores.
- Detecção de comportamento anormal.
- Registro da frequência, amplitude e condições de medição.
- Estimativa de perdas somente quando houver um método de medição adequado.

### Resistores

- Curva tensão versus corrente.
- Resistência estática e diferencial.
- Linearidade.
- Detecção de interrupções e comportamento não linear.
- Estimativa de potência dissipada.

### Indutores

- Curva tensão versus corrente.
- Estimativa de indutância em condições adequadas.
- Identificação de saturação magnética quando o circuito de teste permitir.
- Comparação entre componentes.

### Outros componentes

Permitir perfis extensíveis para varistores, termistores, fusíveis, lâmpadas, células fotossensíveis e outros dispositivos, desde que exista um circuito de teste compatível.

## 11. Análise de sinais e recursos adicionais do osciloscópio

Integre apenas os recursos confirmados para o DHO924S e seu firmware.

- Medições automáticas de amplitude, frequência, período e outros parâmetros disponíveis.
- FFT e análise espectral.
- Operações matemáticas entre canais.
- Estatísticas de medições.
- Detecção de eventos transitórios.
- Medições de tempo e atraso entre sinais.
- Análise de sinais de acionamento.
- Visualização de ruído e componentes espectrais.
- Análise Bode, se suportada e adequada à configuração utilizada.
- Uso de sinais do gerador integrado para excitação de circuitos.
- Decodificação de protocolos digitais, quando disponível e necessária.
- Captura de formas de onda para análise posterior.

Não exponha funções opcionais ou indisponíveis como se estivessem presentes no instrumento. Indique quando um recurso depende de licença, firmware ou equipamento externo.

## 12. Automação de testes

Implemente um sistema de execução de sequências configuráveis.

- Definição de uma sequência de medições.
- Configuração de diferentes amplitudes, frequências e polarizações.
- Repetição de testes.
- Tempo de estabilização entre etapas.
- Critérios de aprovação e reprovação.
- Interrupção por limite de corrente, tensão, potência ou tempo.
- Cancelamento manual.
- Tratamento de falhas e recuperação segura.
- Registro das etapas executadas.
- Execução de lotes de componentes.
- Comparação de componentes do mesmo lote.
- Repetibilidade de configurações.
- Salvamento e carregamento de procedimentos.
- Registro de condições ambientais, quando disponíveis.

A automação não deve iniciar uma etapa de potência se os limites de segurança ou as condições de aquisição não estiverem validados.

## 13. Segurança elétrica

Implemente mecanismos de proteção por software, sem apresentá-los como substitutos de proteção física.

- Limites configuráveis de tensão e corrente.
- Limites de potência calculados quando os dados necessários estiverem disponíveis.
- Verificação de limites antes de iniciar uma sequência.
- Interrupção segura em caso de falha.
- Estado seguro após perda de comunicação.
- Confirmação das configurações de aquisição.
- Prevenção de comandos conflitantes.
- Avisos para circuitos de alta tensão.
- Indicação de polaridade e referências de terra.
- Registro de eventos de segurança.
- Proteção contra execução acidental de uma sequência previamente configurada.

Não prometa desligamento físico de uma fonte externa se o hardware não possuir uma interface de controle para isso. Considere que as entradas do osciloscópio podem compartilhar a referência de terra e que a conexão inadequada pode causar curto-circuito ou choque elétrico.

## 14. Calibração, precisão e incerteza

Crie uma estrutura de calibração e rastreabilidade das medições.

- Calibração de tensão.
- Calibração do canal de corrente calculado.
- Configuração da resistência e tolerância do shunt.
- Compensação de offset.
- Correção de ganho quando validada.
- Registro de data e parâmetros de calibração.
- Identificação da configuração utilizada.
- Estimativa de incerteza quando houver dados suficientes.
- Propagação de incerteza nas grandezas derivadas.
- Identificação de medições fora da faixa calibrada.
- Separação entre valores medidos, calculados e estimados.

Não apresente precisão superior à sustentada pelo instrumento, pelos circuitos externos e pelo método de medição.

## 15. Banco de dados e biblioteca de componentes

Implemente um sistema de organização dos resultados.

- Cadastro de componentes por código e fabricante.
- Categoria do componente.
- Datasheet ou referência documental.
- Parâmetros nominais.
- Limites elétricos.
- Curvas de referência.
- Histórico de medições.
- Comparação de diferentes unidades do mesmo componente.
- Registro de componentes aprovados e reprovados.
- Pesquisa e filtragem.
- Importação e exportação de perfis.
- Versionamento das configurações de teste.

As referências devem ser editáveis e identificadas como provenientes de datasheets, medições próprias ou estimativas.

## 16. Exportação e relatórios

Implemente:

- Exportação de amostras brutas para CSV.
- Exportação de tensão e corrente sincronizadas.
- Exportação de parâmetros calculados.
- Exportação de gráficos em formatos adequados.
- Relatórios em PDF.
- Identificação do instrumento e da conexão utilizada.
- Identificação do componente e do perfil de teste.
- Condições de aquisição e configuração.
- Data e hora.
- Resultados e critérios de aprovação.
- Informações de calibração e limitações.
- Registro de mensagens de erro relevantes.
- Relatórios comparativos entre componentes.
- Reprodutibilidade da análise a partir dos dados salvos.

A exportação dos dados brutos deve preservar a ordem original e as informações necessárias para reconstruir a medição.

## 17. Interface gráfica

Revise a interface existente e organize as funcionalidades em módulos coerentes.

- Painel de conexão e estado do instrumento.
- Painel de configuração de aquisição.
- Configuração de canais.
- Seleção do tipo de componente.
- Configuração do circuito de teste.
- Visualização da forma de onda temporal.
- Visualização da curva I–V.
- Painel de medições e parâmetros.
- Biblioteca de referências.
- Histórico de testes.
- Configuração de automação.
- Exportação de resultados.
- Diagnóstico e logs.
- Indicadores claros de erro, aquisição e processamento.
- Ajuda contextual.
- Validação de entradas.
- Remoção de controles sem implementação funcional.

Evite concentrar todas as funções em uma única tela. Preserve o fluxo de trabalho existente sempre que possível e mantenha as operações de aquisição independentes da interface.

## 18. Desempenho e estabilidade

- Evite bloquear a interface durante a aquisição.
- Utilize mecanismos apropriados de concorrência para comunicação, processamento e visualização.
- Evite transferências repetidas de dados desnecessárias.
- Reduza alocações de memória em operações frequentes.
- Implemente cancelamento e encerramento controlado.
- Libere recursos ao desconectar o instrumento.
- Trate exceções sem ocultar o erro original.
- Evite atualizações gráficas mais frequentes do que o necessário.
- Permita registrar tempos de aquisição, transferência, processamento e renderização.
- Evite perda de amostras silenciosa.
- Registre a origem e o estado de cada conjunto de dados.

## 19. Testes automatizados e simulação

Implemente testes para os componentes críticos.

### Testes unitários

- Conversão de códigos digitais em tensão.
- Cálculo de corrente pelo shunt.
- Cálculo de parâmetros elétricos.
- Reconstrução de curvas.
- Separação de ciclos.
- Tratamento de offsets.
- Conversão de unidades.
- Validação de limites.

### Testes de integração

- Comunicação com o driver.
- Parsing das respostas SCPI.
- Tratamento de timeouts.
- Recuperação de desconexões.
- Sequências de configuração e aquisição.
- Exportação e reimportação de dados.

### Testes gráficos

- Curvas circulares e elípticas.
- Rampas ascendentes e descendentes.
- Curvas com ruído.
- Sinais periódicos.
- Curvas com ramos sobrepostos.
- Amostras incompletas.
- Descontinuidades legítimas.
- Preservação da ordem temporal.

### Simulação

Implemente um instrumento simulado que reproduza respostas documentadas e formas de onda sintéticas. A simulação deve permitir testar a interface, o processamento e a automação sem depender de um osciloscópio conectado.

Não substitua o driver real por uma simulação na execução normal.

## 20. Arquitetura e manutenção

- Preserve a estrutura e as convenções do repositório sempre que possível.
- Separe driver, aquisição, processamento, modelos de componentes e interface.
- Evite duplicação de comandos SCPI.
- Centralize parâmetros e limites.
- Documente interfaces internas.
- Utilize tipagem e validação compatíveis com o projeto.
- Mantenha compatibilidade com as dependências existentes.
- Evite reescritas completas sem necessidade demonstrável.
- Não remova funcionalidades existentes que estejam corretas.
- Documente dependências externas e requisitos de hardware.
- Atualize instruções de instalação e execução.
- Mantenha os novos recursos testáveis de forma independente.

## 21. Recursos avançados para futuras expansões

Prepare a arquitetura para permitir, quando houver suporte de hardware e método de medição:

- Caracterização de componentes em diferentes temperaturas.
- Integração com fontes de alimentação programáveis.
- Controle de cargas eletrônicas.
- Integração com multímetros e medidores LCR.
- Aquisição sincronizada de instrumentos externos.
- Medição automatizada em múltiplas condições.
- Caracterização de componentes dependentes da frequência.
- Comparação estatística entre lotes.
- Análise de degradação ao longo do tempo.
- Detecção de anomalias baseada em parâmetros medidos.
- Classificação assistida de falhas.
- Integração com datasheets e limites de fabricantes.

Essas expansões devem permanecer desativadas ou claramente identificadas enquanto dependerem de hardware, sensores, métodos ou dados ainda não disponíveis.

## 22. Regras obrigatórias de implementação

1. Execute as alterações diretamente no repositório existente.
2. Leia a documentação antes de implementar comandos específicos do instrumento.
3. Não invente comandos SCPI nem presuma compatibilidade entre modelos.
4. Não remova, ordene ou altere amostras originais para corrigir problemas de visualização.
5. Não implemente parâmetros elétricos sem definir o método de cálculo e suas condições de validade.
6. Não crie controles que aparentem funcionar sem uma implementação real.
7. Não oculte exceções, falhas de aquisição ou erros de comunicação.
8. Não substitua o driver real por código simulado.
9. Preserve o comportamento correto das funcionalidades existentes.
10. Crie testes para cada alteração relevante.
11. Execute os testes disponíveis após as modificações e corrija as regressões introduzidas.
12. Se uma funcionalidade depender de hardware externo, identifique explicitamente essa dependência.
13. Se uma função não for suportada pelo DHO924S, não a exponha como funcionalidade disponível.
14. Não declare testes aprovados sem executá-los.
15. Continue implementando as funcionalidades verificadas, sem encerrar o trabalho apenas com uma lista de tarefas.

## 23. Critérios de conclusão

Considere o trabalho concluído somente quando:

- A comunicação com o DHO924S estiver implementada e documentada.
- Os comandos utilizados tiverem respaldo documental.
- A aquisição preservar corretamente a escala e a sincronização das amostras.
- A reconstrução das curvas I–V passar pelos testes automatizados.
- Os problemas de linhas artificiais em curvas de capacitores forem reproduzidos e corrigidos por testes.
- As funcionalidades implementadas estiverem acessíveis pela interface.
- As limitações de hardware estiverem documentadas.
- Os testes executados e seus resultados estiverem registrados.
- As instruções de uso tiverem sido atualizadas.

Ao finalizar, apresente:
1. Arquivos modificados e criados.
2. Funcionalidades efetivamente implementadas.
3. Comandos SCPI utilizados e respectivas referências documentais.
4. Testes executados e resultados reais.
5. Limitações identificadas.
6. Funcionalidades que dependem de hardware externo.
7. Problemas remanescentes que impeçam a conclusão integral.

**Comece inspecionando a documentação e o código atual. Em seguida, implemente as melhorias diretamente, priorizando aquisição, reconstrução correta das curvas, testes automatizados e integração real com o instrumento. Não encerre a execução após produzir a análise inicial.**