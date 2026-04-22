# automated-statusing-tool
Developing an open source implementation of the Automated Statusing Tool (AST) and Universal Overlap Tool (UOT)

## AST-- the engine -- not influenced by user interface
- data inventory, metadata, validation, and registration
- data adaptors / connectors (fetch data intersecting AOI)
- AOI handler (Validate, repair, reproject, prepare)
- overlay (AOI against data registry)
- result (not reporting or records)

**Key Gaurdrails**
1. AOI is normalized once
2. Schema contracts are enforced
3. Inventory and registration is not perfomed at runtime
4. Environment driven configuration

**Future Proofing**
- anticipate asyc for I/O operations
- reduce the overlay engine to geometry operations 
    - The fastest overlay is the one you never run
    - Design for future parallelization (overlays as jobs)

## Out of Current Focus
- UI/UX
- Reporting (maps, tables, documents)
- Document management
