from threading import Lock
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np
from django.test import SimpleTestCase, override_settings

from .services.embeddings import OnnxEmbedder, get_embedder, index_signature


class SmallHostEmbeddingTests(SimpleTestCase):
    def test_quantized_and_torch_indexes_cannot_share_vectors(self):
        with override_settings(EMBEDDING_BACKEND="pytorch"):
            torch_signature = index_signature()
        with override_settings(EMBEDDING_BACKEND="onnx"):
            self.assertNotEqual(index_signature(), torch_signature)

    @override_settings(EMBEDDING_BACKEND="onnx", EMBEDDING_MODEL="intfloat/multilingual-e5-small")
    def test_small_host_never_loads_the_torch_model(self):
        with patch("assistant_app.services.embeddings._load_onnx", return_value="small-model") as onnx, patch(
            "assistant_app.services.embeddings._load_model"
        ) as torch:
            self.assertEqual(get_embedder(), "small-model")
        onnx.assert_called_once()
        torch.assert_not_called()

    def test_pooling_ignores_padding_normalizes_and_limits_batch_memory(self):
        model = OnnxEmbedder.__new__(OnnxEmbedder)
        model.lock = Lock()
        model.input_names = {"input_ids", "attention_mask"}
        model.tokenizer = Mock()
        model.tokenizer.encode_batch.side_effect = lambda texts: [
            SimpleNamespace(ids=[3, 4, 1], attention_mask=[1, 1, 0]) for _ in texts
        ]

        def inference(_, inputs):
            hidden = np.zeros((len(inputs["input_ids"]), 3, 384), dtype=np.float32)
            hidden[:, 0, 0] = 2
            hidden[:, 1, 1] = 2
            hidden[:, 2, 2] = 100  # A padding position must not affect the vector.
            return [hidden]

        model.session = Mock()
        model.session.run.side_effect = inference
        vectors = model.encode(["one", "two", "three", "four", "five"], batch_size=32)
        self.assertEqual(vectors.shape, (5, 384))
        np.testing.assert_allclose(np.linalg.norm(vectors, axis=1), 1, atol=1e-6)
        np.testing.assert_allclose(vectors[:, 2], 0)
        self.assertEqual([len(call.args[1]["input_ids"]) for call in model.session.run.call_args_list], [2, 2, 1])
