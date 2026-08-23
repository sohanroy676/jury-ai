"""Image-understanding subpackage of the parsing agent (v0.3.5).

Modules:
    extract  — pull embedded images out of PDF/PPTX files
    dedupe   — perceptual-hash near-duplicate removal within a submission
    classify — local CLIP zero-shot classification
    describe — vision-LLM structural descriptions via Groq
    pipeline — orchestration: dedupe -> cache -> classify -> route -> describe
"""
