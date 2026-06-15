"""대표홈페이지(HOM/MHM)와 별개의 단순 접속 점검 시스템들을 위한 공용 프레임워크.

FP·HRP·HWTC·CHBOT 처럼 자체 업무가 대표홈페이지와 완전히 분리된 시스템은
현재 "메인화면 접속"만 점검하면 되므로, 로그인/인증에 묶인 HOM·MHM 의 무거운
``login_common`` 을 재사용하지 않고 이 경량 프레임워크를 공유한다.

이 패키지에는 manifest.yaml 이 없으므로 레지스트리가 시스템으로 인식하지 않는다.
각 시스템의 ``executor.py`` 가 :func:`create_access_executor` 를 호출해 자신만의
base_url·모바일 여부·실행 모드를 주입한다.
"""
