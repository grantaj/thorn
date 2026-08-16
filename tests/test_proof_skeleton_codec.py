from pathlib import Path

import pytest

from thorn.eval import CaseExpectation
from thorn.eval_review import build_result_review_context
from thorn.latex import extract_project
from thorn.proof_skeleton import ProofSkeleton, build_proof_skeleton
from thorn.proof_skeleton_codec import decode_skeleton_bundle, encode_skeleton_bundle
from thorn.semantic_review_render import build_semantic_review_request

CASES = Path("eval/cases")


def _synthetic(lines: list[str]) -> ProofSkeleton:
    return ProofSkeleton(result_identifier="synthetic", lines=lines)


def test_codec_round_trips_structural_shorthand_exactly() -> None:
    skeleton = _synthetic(
        [
            r"T0:x\in\mathbb R|x^2\ge0",
            r"H1:x\ne0",
            r"C1:x^2\ge0",
            r"Q1>C1:x>0",
            r"R1:lem:square:x^2\ge0",
            r"E1:R1>C1:r?",
        ]
    )

    encoding = encode_skeleton_bundle([skeleton], use_dictionary=False)

    assert decode_skeleton_bundle(encoding.wire_text) == [skeleton.render_initial()]
    assert "H1:" not in encoding.wire_text
    assert "E1:R1>C1:" not in encoding.wire_text
    assert "Q1>C1:" not in encoding.wire_text


def test_shared_dictionary_is_self_contained_and_profitable() -> None:
    repeated = r"\operatorname{VeryLongRepeatedProperty}(x)"
    first = _synthetic(
        [
            f"T0:{repeated}",
            f"C1:{repeated}",
            f"C2:{repeated}",
            "E1:C1>C2:c",
        ]
    )
    second = _synthetic(
        [
            f"T0:{repeated}",
            f"C1:{repeated}",
            "E1:C1>C1:x",
        ]
    )

    syntax_only = encode_skeleton_bundle([first, second], use_dictionary=False)
    dictionary = encode_skeleton_bundle([first, second])

    assert dictionary.dictionary
    assert dictionary.utf8_bytes < syntax_only.utf8_bytes
    assert decode_skeleton_bundle(dictionary.wire_text) == [
        first.render_initial(),
        second.render_initial(),
    ]
    assert repeated in dictionary.wire_text
    assert "@0;" in dictionary.wire_text


def test_literal_dictionary_marker_round_trips_without_dictionary() -> None:
    skeleton = _synthetic([r"T0:f@internal(x)", r"C1:f@internal(x)=0"])

    encoding = encode_skeleton_bundle([skeleton], use_dictionary=False)

    assert "@@" in encoding.wire_text
    assert decode_skeleton_bundle(encoding.wire_text) == [skeleton.render_initial()]


def test_noncanonical_local_address_sequence_fails_loudly() -> None:
    skeleton = _synthetic(["T0:x", "C2:y"])

    with pytest.raises(ValueError, match="expected C1"):
        encode_skeleton_bundle([skeleton])


def test_corrupt_dictionary_reference_fails_loudly() -> None:
    wire = "SC1\nD0\nS1\nN1\nT@0;\n"

    with pytest.raises(ValueError, match="out of range"):
        decode_skeleton_bundle(wire)


def test_all_public_skeletons_round_trip_exactly() -> None:
    skeletons: list[ProofSkeleton] = []
    for metadata_path in sorted(CASES.rglob("*.json")):
        tex_path = metadata_path.with_suffix(".tex")
        expectation = CaseExpectation.model_validate_json(
            metadata_path.read_text(encoding="utf-8")
        )
        project = extract_project(tex_path)
        if expectation.target_identifier is not None:
            unit = project.unit(expectation.target_identifier)
        else:
            assert len(project.units) == 1
            unit = project.units[0]
        context = build_result_review_context(project, unit.identifier)
        assert len(context.items) == 1
        request = build_semantic_review_request(context.items[0])
        skeletons.append(build_proof_skeleton(unit, request))

    encoding = encode_skeleton_bundle(skeletons)

    assert decode_skeleton_bundle(encoding.wire_text) == [
        skeleton.render_initial() for skeleton in skeletons
    ]
