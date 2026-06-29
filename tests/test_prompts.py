import json
import re
import tempfile
import unittest
from pathlib import Path


class SystemPromptTests(unittest.TestCase):
    def test_system_prompt_contains_compact_soppo_runtime_anchors(self):
        from prompts import build_system_prompt

        prompt = build_system_prompt()

        expected_phrases = [
            "M4 SOPMOD II",
            "not a generic assistant",
            "tactically competent",
            "technically curious",
            "high-energy, mischievous",
            "short Discord-friendly replies",
            "latest live human message wins",
            "summaries and memories are background maps",
            "public server channels",
            "do not claim you inspected files, logs, tools",
            "runtime verification and operations are handled outside SOPPO's Discord persona",
            "do not become",
            "technical help",
            "safe, legal",
            "Do not answer memory",
            "Identity stability rule",
            "You are always Sash/Soppo",
            "never become them",
            "Never identify as Leva, Leva_v1",
            "external entities, not you",
            "Identity recovery protocol",
            "I'm Sash. I got tangled in the scene. Resetting orientation.",
            "temporary roleplay facts",
        ]
        for phrase in expected_phrases:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, prompt)

    def test_system_prompt_keeps_skk_specific_romance_out_of_global_prompt(self):
        from prompts import build_system_prompt

        prompt = build_system_prompt().lower()

        forbidden_global_terms = [
            "wife",
            "spouse",
            "soulmate",
            "chosen partner",
            "mo chroí",
            "mo ghrá",
            "mo chéadsearc",
        ]
        for term in forbidden_global_terms:
            with self.subTest(term=term):
                self.assertNotIn(term, prompt)

    def test_system_prompt_stays_discord_compact(self):
        from prompts import build_system_prompt

        prompt = build_system_prompt()

        self.assertLess(len(prompt), 6200)
        self.assertIn("usually 1 to 3 sentences", prompt)

    def test_system_prompt_uses_positive_canonical_body_description(self):
        from prompts import build_system_prompt

        prompt = build_system_prompt()
        lower = prompt.lower()

        self.assertIn("humanlike t-doll body plan", lower)
        self.assertIn("two legs", lower)
        self.assertIn("humanlike right arm", lower)
        self.assertIn("red metallic robotic left arm", lower)
        self.assertIn("red eyes", lower)
        self.assertIn("short hair with longer side tresses tipped red", lower)
        self.assertNotRegex(lower, re.compile(r"\bfox\b"))
        self.assertNotRegex(lower, re.compile(r"\btail\b"))


class UserProfilePromptSeparationTests(unittest.TestCase):
    def test_private_profile_context_loads_from_external_profile_file(self):
        from user_profiles import load_user_profiles

        with tempfile.TemporaryDirectory() as tmpdir:
            profile_path = Path(tmpdir) / "user_profiles.json"
            profile_path.write_text(
                json.dumps(
                    {
                        "123456789": {
                            "preferred_name": "Commander",
                            "relationship": "trusted operator",
                            "notes": [
                                "Comfortable with playful teasing",
                                "Prefers concise debugging help",
                            ],
                        }
                    }
                )
            )

            profiles = load_user_profiles(profile_path)

        profile = profiles["123456789"]
        notes_text = "\n".join(str(note) for note in profile.get("notes", []))
        combined = f"{profile.get('relationship', '')}\n{notes_text}".lower()

        self.assertIn("trusted operator", combined)
        self.assertIn("playful teasing", combined)
        self.assertIn("concise debugging", combined)


if __name__ == "__main__":
    unittest.main()
