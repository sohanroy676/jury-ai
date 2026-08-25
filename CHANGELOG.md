# Changelog

All notable changes to this project are documented here.
Format follows Keep a Changelog. Generated from Conventional Commits — regenerate via `/commit` workflow, do not hand-edit.

## [v1.1.0] - 2026-08-25

### Bug Fixes

* **portal:** Carry shortlist cutoff into export URLs ([f4885e6](https://github.com/sohanroy676/jury-ai/commit/f4885e6bdce26c6df850df85adb753af7efa76a7))

### Features

* **portal:** Pre-submit validation, replace flow, stage tracker ([9c47180](https://github.com/sohanroy676/jury-ai/commit/9c47180c1cdc0a9891544ca208d27e1ee9f27555))
* **submissions:** Allow re-submission with archived history ([b1db34e](https://github.com/sohanroy676/jury-ai/commit/b1db34eaaf1ba1f005f8a7f9c209d6f1aa90c6a1))

## [v1.0.0] - 2026-08-25

### Bug Fixes

* **test:** Align criterion label assertion and EOF formatting ([8ed4fb5](https://github.com/sohanroy676/jury-ai/commit/8ed4fb5e60fde288a187eb2fd24bc3289ba03b26))
* **cors:** Allow PUT preflight for rubric saves ([8976c52](https://github.com/sohanroy676/jury-ai/commit/8976c520029e9342eada967e33ac1af347711592))

### Features

* Implement frontend ([971a362](https://github.com/sohanroy676/jury-ai/commit/971a3620cbb098f033c9052a30dd5485157bb8ac))

## [v0.7.0] - 2026-08-25

### Features

* **feedback:** Add feedback agent and exports ([c8359a1](https://github.com/sohanroy676/jury-ai/commit/c8359a130cdee20d580d71238ac3085f073f03e7))

## [v0.6.0] - 2026-08-24

### Features

* **ranking:** Add weighted ranking engine and rubric config ([dfe7007](https://github.com/sohanroy676/jury-ai/commit/dfe7007ae3569b8b87a42f2a5c67e8d50459a224))

## [v0.5.0] - 2026-08-24

### Features

* **scoring:** Split scoring into four parallel specialist agents ([e216eb4](https://github.com/sohanroy676/jury-ai/commit/e216eb471666972c5d2ff91b92bb60525f7b9a75))

## [v0.4.0] - 2026-08-24

### Bug Fixes

* **version:** Centralize project version into single source ([7a7e3b5](https://github.com/sohanroy676/jury-ai/commit/7a7e3b593bcb504bfa6790e9e7684a27cac8e7e5))

### Features

* **api:** Add submission list and detail read endpoints ([ed72af1](https://github.com/sohanroy676/jury-ai/commit/ed72af1f0fa7045b2c5a9025497b3b6e28aa4556))

## [v0.3.6] - 2026-08-24

### Bug Fixes

* **parsing:** Use gemini-3.6-flash default model ([e559add](https://github.com/sohanroy676/jury-ai/commit/e559add5d8bbef2c3b71d9f43ad194f6fa834e9f))
* **images:** Rescue misread diagrams, stop describing decoration ([9065e11](https://github.com/sohanroy676/jury-ai/commit/9065e1103b78e155003b68a7de609bf60333b28e))

### Features

* **parsing:** Add Gemini vision describer option ([c4a17a1](https://github.com/sohanroy676/jury-ai/commit/c4a17a160e990bd621a48e92a215d2c6ad574558))

## [v0.3.5] - 2026-08-23

### Bug Fixes

* **parsing:** Handle unterminated vision reasoning blocks ([40e21e8](https://github.com/sohanroy676/jury-ai/commit/40e21e8af7b7fcd8b9b55d2b3f3edaeb45cf1b4c))
* **services:** Return none when parsed submission missing ([b6e4097](https://github.com/sohanroy676/jury-ai/commit/b6e4097e42b0d602a490cd9652271f265862bac9))
* **parsing:** Stop doomed vision calls once rate-limited ([89daf5b](https://github.com/sohanroy676/jury-ai/commit/89daf5bd540138988553a14fcce049c9635b7c0f))

### Features

* **parsing:** Add image understanding pipeline ([0292b7f](https://github.com/sohanroy676/jury-ai/commit/0292b7f15e2d25dfdf4fc846115fa32147ec2823))
* **scoring:** Merge image descriptions into input ([a85e92c](https://github.com/sohanroy676/jury-ai/commit/a85e92c197ce7c8a7196552f2fd89ec29926a338))

## [v0.3.0] - 2026-08-22

### Bug Fixes

* **scoring:** Switch default model to openai/gpt-oss-120b ([869aaf7](https://github.com/sohanroy676/jury-ai/commit/869aaf73e5390324581b61e42fcbab25eba4066b))
* **parsing:** Normalize unicode dashes to ascii hyphens ([d5172bf](https://github.com/sohanroy676/jury-ai/commit/d5172bf663f3ca88411ce218b64f5d101e3fdf05))

### Features

* **scoring:** Add single scoring agent with Groq integration (v0.3.0) ([51e7fef](https://github.com/sohanroy676/jury-ai/commit/51e7fefa2cb7040833ea98fec17714409f402130))

## [v0.2.0] - 2026-08-21

### Bug Fixes

* **cors:** Configure frontend origins and add CORS tests ([6179319](https://github.com/sohanroy676/jury-ai/commit/617931949f7eb0019a6f451d6110297761c323cb))

### Features

* **parsing:** Add PDF/PPTX text extraction agent (v0.2.0) ([ea558e7](https://github.com/sohanroy676/jury-ai/commit/ea558e7f372b0cda890c7cfb9bb9f7d89355fbdd))

## [v0.1.0] - 2026-08-20

### Features

* **v0.1.0:** Scaffold project skeleton with upload portal and Supabase wiring ([c8ca8be](https://github.com/sohanroy676/jury-ai/commit/c8ca8beee7a4b67b341e573e670a7357e40cf729))
