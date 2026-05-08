```mermaid
classDiagram
    DataRegistry --|> DataAdapters
    DataAdapters --|> DataValidators
    DataValidators --|> datasets_yaml
    datasets_config --|> datasets_yaml
    inputAOI --|> AOIAdapters
    AOIAdapters --|> AOIValidators
    AOIValidators --|> AOIObject
    AOIObject --|> Operators
    datasets_yaml --|> Operators
    Operators --|> ResultsObject
    results_config --|> ResultsObject
    
    class DataRegistry{
      input
      type: xls
    }
    class DataAdapters{
      +fcbc()
    }
    class DataValidators{
      +inspect()
      +validate()
      +enrich()
    }
    class datasets_yaml{
        all datasets 
        type: yaml
        type:gdf
    }
    class datasets_config{
        data configuration
    }
    class inputAOI{
        input
        type: kml
        type: oracle
        type: tantalis
        type: geographic
    }
    class AOIAdapters{
        +kml()
        +oracle()
    }
    class AOIValidators{
        +inspect()
        +validate()
        +enrich()
    }
    class AOIObject{
        configured 
        type: gdf
    }
    class Operators{
        +adjacent()
        +distance()
        +overlay()
        +union()
        +buffer()
    }
    class ResultsObject{
        type: gdf
    }
    class results_config{
        resultant configuration
    }
