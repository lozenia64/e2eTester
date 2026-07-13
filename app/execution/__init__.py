"""실행 경계(Execution boundary).

오케스트레이션(상태머신)과 브라우저 실행(부작용)을 가르는 포트와 그 어댑터를 담는다.
상태머신은 ``ExecutionGateway`` 포트에만 의존하고, 실제 브라우저 구동·스레드 모델·런타임
수명은 어댑터(``WorkerExecutionGateway`` → 워커 프로세스의 ``SessionServer``; SIM 은
``SimulatedExecutionGateway``) 뒤에 숨긴다. 동일 포트로 향후 다른 워커/Playwright MCP
구현체로 교체할 수 있다.
"""
