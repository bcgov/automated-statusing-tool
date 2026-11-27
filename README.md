# automated-statusing-tool
Developing an open source implementation of the Automated Statusing Tool (AST) and Universal Overlap Tool (UOT)

**Under Development**


# Application Overview
```mermaid
flowchart LR
  subgraph Client
    UI[Web app]
  end
  subgraph Services
    API[FastAPI]
    Auth[Auth service]
    Q[Valkey]
    Engine[Engine Worker]
  end
  subgraph Storage
    S3[(APP DATA S3)]
    PVC[(SQLITE)]
  end
  UI --> API
  API --> Auth
  API <--> S3
  API <--> PVC
  API --> Q
  Q --> Engine
  Engine --> S3
  Engine --> API
  PVC --> Engine
  Auth -. token .-> UI
```