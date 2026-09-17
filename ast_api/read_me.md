This folder has been created to hold the api created for the ast_engine. 

The api will communicate between the frontend and the engine itself. '

The same approached used by the burn severity application ([link here](https://github.com/bcgov/burn-severity-map)) was used as template to follow, in addition to Corey Schafer's FastAPI Youtube Tutorial ([link here](https://www.youtube.com/playlist?list=PL-osiE80TeTsak-c-QsVeg0YYG_0TeyXI))

Wills thoughts
1. will need to make distinct uv projects for engine and api
2. should create another folder for shared models AstJob, JobStatus, and perhaps manifest
3. settings should not be shared - engine and api will be distinct images / containers
4. Need to do some research on polling redis for status from the api. Instead status should be tracked in the SQLite db and polled from there
5. 