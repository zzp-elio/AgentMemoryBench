"""OpenAI API 与配置层测试。

本文件验证项目能从 `.env` 读取 OpenAI 配置，并用 OpenAI Python SDK
对 `gpt-4o-mini` 发起一次最小 smoke test。测试不会打印 API key。
"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest


from memory_benchmark.config import OpenAISettings, load_path_settings, load_settings
from memory_benchmark.core import ConfigurationError


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.unit
class OpenAIConfigTests(unittest.TestCase):
    """测试 OpenAI 配置读取和安全展示行为。"""

    def test_load_path_settings_reads_project_directories_without_openai_key(self):
        """测试路径配置可独立读取，不依赖 OpenAI API key。

        输入:
            临时项目目录路径。

        输出:
            PathSettings: 派生出的 data/models/outputs/third_party 目录路径。
        """

        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            paths = load_path_settings(project_root=project_root)

        self.assertEqual(paths.project_root, project_root.resolve())
        self.assertEqual(paths.data_root, project_root.resolve() / "data")
        self.assertEqual(paths.models_root, project_root.resolve() / "models")
        self.assertEqual(paths.outputs_root, project_root.resolve() / "outputs")
        self.assertEqual(paths.third_party_root, project_root.resolve() / "third_party")
        self.assertEqual(
            paths.third_party_benchmarks_root,
            project_root.resolve() / "third_party" / "benchmarks",
        )
        self.assertEqual(
            paths.third_party_methods_root,
            project_root.resolve() / "third_party" / "methods",
        )

    def test_resolve_third_party_method_path_requires_existing_method_root(self):
        """测试第三方 method 路径解析会校验 method 根目录存在且拒绝越界。

        输入:
            临时项目目录下存在 `third_party/methods/MemoryOS-main` 目录。

        输出:
            PathSettings: 可解析 method 内部文件路径；缺少 method 根目录或越界路径时抛配置异常。
        """

        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            method_root = project_root / "third_party" / "methods" / "MemoryOS-main"
            method_root.mkdir(parents=True)
            sibling_method_root = (
                project_root / "third_party" / "methods" / "SiblingMethod-main"
            )
            sibling_method_root.mkdir()

            paths = load_path_settings(project_root=project_root)

            resolved = paths.resolve_third_party_method_path(
                "MemoryOS-main",
                "eval",
                "runner.py",
            )
            self.assertEqual(resolved, (method_root.resolve() / "eval" / "runner.py").resolve())

            self.assertEqual(
                paths.resolve_third_party_method_path("MemoryOS-main"),
                method_root.resolve(),
            )

            with self.assertRaises(ConfigurationError):
                paths.resolve_third_party_method_path("Missing-main", "eval.py")

            with self.assertRaises(ConfigurationError):
                paths.resolve_third_party_method_path("MemoryOS-main", "..", "escape.py")

            with self.assertRaises(ConfigurationError):
                paths.resolve_third_party_method_path(
                    "MemoryOS-main/../SiblingMethod-main",
                    "eval.py",
                )

    def test_load_settings_reads_openai_key_and_base_url_from_env_file(self):
        """测试配置层能从 `.env` 读取 `OPENAI_KEY` 和 `BASE_URL`。

        输入:
            临时项目目录中的 `.env` 文件，包含 fake key 和 fake base URL。

        输出:
            AppSettings: `openai` 配置使用文件中的 key、base URL 和固定模型。
        """

        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            env_file = project_root / ".env"
            env_file.write_text(
                "OPENAI_KEY=sk-test-from-file\nBASE_URL=https://example.test/v1\n",
                encoding="utf-8",
            )

            with patch.dict(os.environ, {}, clear=True):
                settings = load_settings(project_root=project_root)

        self.assertEqual(settings.openai.api_key, "sk-test-from-file")
        self.assertEqual(settings.openai.base_url, "https://example.test/v1")
        self.assertEqual(settings.openai.model, "gpt-4o-mini")

    def test_openai_settings_redacts_api_key_for_debug_output(self):
        """测试配置对象不会在 debug 字典中暴露完整 API key。

        输入:
            含 fake key 的 OpenAISettings。

        输出:
            dict: 可安全写入日志的配置摘要，key 只保留前后少量字符。
        """

        settings = OpenAISettings(
            api_key="sk-test-1234567890",
            base_url="https://example.test/v1",
        )

        safe_dict = settings.to_safe_dict()

        self.assertEqual(safe_dict["api_key"], "sk-t...7890")
        self.assertNotIn("sk-test-1234567890", str(safe_dict))

    def test_missing_openai_key_raises_configuration_error(self):
        """测试缺少 API key 时抛出项目配置异常。

        输入:
            没有 `OPENAI_KEY` 或 `OPENAI_API_KEY` 的临时项目目录。

        输出:
            ConfigurationError: 提示调用方配置缺失，而不是泄漏底层 KeyError。
        """

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(os.environ, {}, clear=True):
                with self.assertRaises(ConfigurationError):
                    load_settings(project_root=Path(temp_dir))


@pytest.mark.api
class OpenAIAPISmokeTests(unittest.TestCase):
    """测试当前 `.env` 中的 OpenAI API 配置是否可用。"""

    def test_gpt_4o_mini_chat_completion_smoke_test(self):
        """测试 `gpt-4o-mini` 能通过当前 `.env` 完成一次最小调用。

        输入:
            根目录 `.env` 中的 `OPENAI_KEY` 和 `BASE_URL`。

        输出:
            str: 模型返回的简短文本；测试只断言非空，不打印 API key。
        """

        try:
            settings = load_settings(project_root=ROOT)
        except ConfigurationError as error:
            self.skipTest(str(error))

        from openai import OpenAI

        client = OpenAI(**settings.openai.to_client_kwargs())
        response = client.chat.completions.create(
            model=settings.openai.model,
            messages=[
                {
                    "role": "system",
                    "content": "You are a smoke test. Reply with exactly: ok",
                },
                {"role": "user", "content": "ping"},
            ],
            temperature=0,
            max_tokens=5,
        )

        content = response.choices[0].message.content
        self.assertIsInstance(content, str)
        self.assertGreater(len(content.strip()), 0)


if __name__ == "__main__":
    unittest.main()
