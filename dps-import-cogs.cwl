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
# x-release-please-start-version
s:softwareVersion: 0.2.0
s:version: 0.2.0
# x-release-please-end
s:keywords:
  - STAC
  - metadata
  - object storage
  - MAAP
$graph:
  - class: Workflow
    id: generate_stac_items
    label: DPS STAC Item Generator
    doc: Generate a self-contained STAC catalog for selected files in object storage.
    inputs:
      source:
        label: Source location
        doc: Object storage URL of the files to describe, for example s3://bucket/prefix/.
        type: string
      region:
        label: AWS region
        doc: Region in which the storage container exists.
        type: string
        default: us-west-2
      include_extensions:
        label: Included extensions
        doc: Comma-separated extensions to include. Omit to use defaults; an empty string includes all files.
        type: ["null", string]
        default: null
      exclude_extensions:
        label: Excluded extensions
        doc: Comma-separated extensions to exclude. Exclusions override inclusions.
        type: string
        default: ''
      config:
        label: Cataloging configuration
        doc: Optional JSON path selection and grouping configuration.
        type: ["null", File]
        default: null
    outputs:
      output:
        type: Directory
        outputSource: process/output
    steps:
      process:
        run: '#main'
        in:
          source: source
          region: region
          include_extensions: include_extensions
          exclude_extensions: exclude_extensions
          config: config
        out:
          - output
  - class: CommandLineTool
    id: main
    requirements:
      DockerRequirement:
        # x-release-please-start-version
        dockerPull: ghcr.io/maap-project/dps-import-cogs:v0.2.0
        # x-release-please-end
      NetworkAccess:
        networkAccess: true
      ResourceRequirement:
        ramMin: 8192
        coresMin: 1
        outdirMin: 8192
    baseCommand:
      - /app/dps-import-cogs/.venv/bin/dps-stac-item-generator
      - --output_dir
      - output
    successCodes:
      - 0
    inputs:
      source:
        type: string
        inputBinding:
          position: 1
          prefix: '--source'
      region:
        type: string
        default: us-west-2
        inputBinding:
          position: 2
          prefix: '--region'
      include_extensions:
        type: ["null", string]
        default: null
        inputBinding:
          position: 3
          prefix: '--include-extensions='
          separate: false
      exclude_extensions:
        type: string
        default: ''
        inputBinding:
          position: 4
          prefix: '--exclude-extensions='
          separate: false
      config:
        type: ["null", File]
        inputBinding:
          position: 5
          prefix: '--config'
    outputs:
      output:
        type: Directory
        outputBinding:
          glob: output
