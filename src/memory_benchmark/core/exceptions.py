"""框架级领域异常。

本模块只放跨层共享的错误类型，方便 runner、adapter、CLI 在捕获异常时
区分“用户输入不支持”“数据路径缺失”“注册冲突”等可 debug 场景。
"""


class MemoryBenchmarkError(Exception):
    """所有本项目自定义异常的基类。"""


class DatasetNotFoundError(MemoryBenchmarkError):
    """benchmark adapter 需要的数据文件或目录不存在。"""

    def __init__(self, benchmark: str, relative_path: str):
        """构造缺失数据路径错误。

        输入:
            benchmark: 触发错误的 benchmark 名称。
            relative_path: 相对项目根目录的数据路径。

        输出:
            None。异常消息会包含 benchmark 和路径，方便 debug。
        """

        super().__init__(f"{benchmark} expected dataset path missing: {relative_path}")
        self.benchmark = benchmark
        self.relative_path = relative_path


class UnknownBenchmarkError(MemoryBenchmarkError):
    """请求了当前 registry 未注册的 benchmark。"""

    def __init__(self, benchmark: str, supported: list[str]):
        """构造未知 benchmark 错误。

        输入:
            benchmark: 用户请求但未注册的 benchmark 名称。
            supported: 当前 registry 支持的 benchmark 名称列表。

        输出:
            None。异常消息会列出可用 benchmark，便于修正命令。
        """

        supported_text = ", ".join(supported) if supported else "<none>"
        super().__init__(f"Unknown benchmark '{benchmark}'. Supported: {supported_text}")
        self.benchmark = benchmark
        self.supported = supported


class AdapterAlreadyRegisteredError(MemoryBenchmarkError):
    """同名 benchmark adapter 重复注册。"""

    def __init__(self, benchmark: str):
        """构造重复注册错误。

        输入:
            benchmark: 重复注册的 benchmark 名称。

        输出:
            None。异常消息会指出冲突名称。
        """

        super().__init__(f"Benchmark adapter already registered: {benchmark}")
        self.benchmark = benchmark


class ConfigurationError(MemoryBenchmarkError):
    """项目运行配置缺失或格式不合法。"""

    def __init__(self, message: str):
        """构造配置错误。

        输入:
            message: 面向开发者的错误说明，不能包含 API key 等敏感值。

        输出:
            None。异常消息用于 CLI、测试或 runner 给出可读诊断。
        """

        super().__init__(message)


class DatasetValidationError(MemoryBenchmarkError):
    """统一数据集校验失败。"""

    def __init__(self, message: str):
        """构造数据集校验错误。

        输入:
            message: 具体字段或结构问题，不能包含 method 私有凭据。

        输出:
            None。异常消息用于 adapter、runner 或测试定位非法数据。
        """

        super().__init__(f"Dataset validation failed: {message}")


class JudgeOutputError(MemoryBenchmarkError):
    """LLM judge 返回内容无法解析或不符合约定。"""

    def __init__(self, message: str):
        """构造 judge 输出错误。

        输入:
            message: 输出格式问题说明，不能包含 API key 等敏感值。

        输出:
            None。异常消息用于 evaluator 和测试定位 judge 输出问题。
        """

        super().__init__(f"Judge output invalid: {message}")


class DataLeakageError(MemoryBenchmarkError):
    """检测到 private data 可能泄漏给 method。"""

    def __init__(self, message: str):
        """构造数据泄漏风险错误。

        输入:
            message: 泄漏风险位置和字段说明。

        输出:
            None。异常消息帮助 adapter 在进入 method 前失败。
        """

        super().__init__(f"Private data leakage risk: {message}")
