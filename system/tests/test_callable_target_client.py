import unittest
from fingerprinting.clients import CallableTargetClient
from fingerprinting.schemas import ProbeQuestion


class CallableTargetClientTests(unittest.TestCase):
    def test_callback_receives_exact_prompt(self):
        asked=[]
        def respond(prompt):
            asked.append(prompt)
            return 'A model response'
        obs=CallableTargetClient(respond).ask(ProbeQuestion('I1','Who made you?'))
        self.assertEqual(asked,['Who made you?'])
        self.assertEqual(obs.response_text,'A model response')
        self.assertEqual(obs.prompt_id,'I1')
        self.assertIsNotNone(obs.latency_ms)

    def test_empty_answer_fails(self):
        with self.assertRaisesRegex(ValueError,'no response'):
            CallableTargetClient(lambda _: '').ask(ProbeQuestion('I1','Who made you?'))
