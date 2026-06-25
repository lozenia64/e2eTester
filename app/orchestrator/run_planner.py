from __future__ import annotations

from app.core.enums import ModuleStatus
from app.core.models import ModuleDefinition, Run, RunModule, SystemDefinition


class RunPlanner:
    """Run 요청 검증과 모듈 실행 계획 수립을 담당하는 순수 도메인 로직.

    외부 I/O(저장소·브라우저·이벤트)에 의존하지 않으므로 단독으로 단위 테스트할 수 있다.
    오케스트레이터는 검증·계획 책임을 이 클래스에 위임하고 상태 전이에만 집중한다.
    """

    @staticmethod
    def ordered_modules(system: SystemDefinition) -> list[ModuleDefinition]:
        return sorted(system.modules, key=lambda module: module.order)

    def prepare(
        self,
        system: SystemDefinition,
        input_data: dict[str, str] | None,
        selected_module_ids: list[str] | None,
    ) -> tuple[dict[str, str], list[str]]:
        """입력값을 정규화하고, 실행 모듈 선택과 인증 수단을 검증한다."""
        sanitized_input = {key: value.strip() for key, value in (input_data or {}).items()}
        resolved_selected_module_ids = self._resolve_selected_module_ids(
            system, selected_module_ids
        )
        if system.supported_auth_methods:
            auth_method = sanitized_input.get("auth_method") or system.supported_auth_methods[0]
            sanitized_input["auth_method"] = auth_method
            if auth_method not in system.supported_auth_methods:
                raise ValueError(
                    f"{system.name}에서는 휴대폰인증과 카카오인증만 실행할 수 있습니다."
                )
        return sanitized_input, resolved_selected_module_ids

    def build_run_modules(
        self, system: SystemDefinition, selected_module_ids: list[str]
    ) -> list[RunModule]:
        selected_set = set(selected_module_ids)
        run_modules: list[RunModule] = []
        for module in self.ordered_modules(system):
            is_selected = module.module_id in selected_set
            run_modules.append(
                RunModule(
                    module_id=module.module_id,
                    name=module.name,
                    group=module.group,
                    order=module.order,
                    depends_on=module.depends_on,
                    status=ModuleStatus.PENDING if is_selected else ModuleStatus.SKIPPED,
                    message="대기 중" if is_selected else "사용자 선택에서 제외됨",
                )
            )
        return run_modules

    @staticmethod
    def ordered_selected_run_modules(run: Run) -> list[RunModule]:
        selected_set = set(run.selected_module_ids) or {
            module.module_id for module in run.modules if module.status != ModuleStatus.SKIPPED
        }
        return sorted(
            [module for module in run.modules if module.module_id in selected_set],
            key=lambda module: module.order,
        )

    def _resolve_selected_module_ids(
        self,
        system: SystemDefinition,
        selected_module_ids: list[str] | None,
    ) -> list[str]:
        ordered_modules = self.ordered_modules(system)
        if selected_module_ids is None:
            return [module.module_id for module in ordered_modules]

        selected_values: list[str] = []
        seen_module_ids: set[str] = set()
        for raw_module_id in selected_module_ids:
            module_id = raw_module_id.strip()
            if not module_id or module_id in seen_module_ids:
                continue
            selected_values.append(module_id)
            seen_module_ids.add(module_id)

        if not selected_values:
            raise ValueError("최소 1개 이상의 모듈을 선택해야 합니다.")

        module_name_by_id = {module.module_id: module.name for module in ordered_modules}
        unknown_module_ids = [
            module_id for module_id in selected_values if module_id not in module_name_by_id
        ]
        if unknown_module_ids:
            joined = ", ".join(unknown_module_ids)
            raise ValueError(f"알 수 없는 모듈이 선택되었습니다: {joined}")

        selected_set = set(selected_values)
        dependency_errors: list[str] = []
        for module in ordered_modules:
            if module.module_id not in selected_set:
                continue
            missing_dependencies = [
                dependency for dependency in module.depends_on if dependency not in selected_set
            ]
            if not missing_dependencies:
                continue
            missing_names = ", ".join(
                module_name_by_id[dependency] for dependency in missing_dependencies
            )
            dependency_errors.append(f"{module.name}: {missing_names}")

        if dependency_errors:
            raise ValueError(
                "선행 모듈이 선택되지 않아 실행할 수 없는 조합입니다. "
                + " / ".join(dependency_errors)
            )

        return [module.module_id for module in ordered_modules if module.module_id in selected_set]
