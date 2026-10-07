cwlVersion: v1.2
$namespaces:
  s: https://schema.org/
$schemas:
  - >-
    https://raw.githubusercontent.com/schemaorg/schemaorg/refs/heads/main/data/releases/9.0/schemaorg-current-http.rdf
s:author:
  - class: s:Organization
    s:name: MAAP Project
s:codeRepository: https://github.com/MAAP-Project/dps-import-cogs
s:softwareVersion: 0.1.0
s:version: 0.1.0
s:keywords:
  - STAC
  - synthetic data
  - happy face
  - MAAP
$graph:
  - class: Workflow
    id: generate_happy_face_demo
    label: Self-contained Happy Face DPS Demo
    doc: Generate two synthetic RGB tiles and return their COGs bundled with a self-contained STAC catalog.
    inputs: {}
    outputs:
      output:
        type: Directory
        outputSource: process/output
    steps:
      process:
        run: '#main'
        in: {}
        out:
          - output
  - class: CommandLineTool
    id: main
    requirements:
      DockerRequirement:
        dockerPull: ghcr.io/maap-project/dps-import-cogs:happy-face-demo-v0.1.0
      ResourceRequirement:
        ramMin: 8192
        coresMin: 1
        outdirMin: 8192
    baseCommand:
      - /app/dps-import-cogs/.venv/bin/happy-face-dps-demo
      - --output_dir
      - output
    successCodes:
      - 0
    inputs: {}
    outputs:
      output:
        type: Directory
        outputBinding:
          glob: output
