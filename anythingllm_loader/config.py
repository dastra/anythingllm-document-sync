import os
import pathlib
import yaml

CONFIG_DIR = pathlib.Path.home() / ".anythingllm-sync"
CONFIG_FILE = 'config.yaml'


DEFAULT_URL = "http://localhost:3001"

# Config file looks like this:
# api-key: WFSDFD-ASDAFDFD-Q8M53TR-AAAAS48
# workspace-slug: aws
# anythingllm-url: http://localhost:3001   # optional, defaults to http://localhost:3001
# file-paths:
#   - /Users/username/Documents/
# directory-excludes:
#   - .obsidian
# file-excludes:
#   - .DS_Store

class AnythingLLMConfig:

    # create init method including all config keys
    def __init__(self, api_key: str, file_paths: list, directory_excludes: list, file_excludes: list,
                 workspace_slug: str, anythingllm_url: str = DEFAULT_URL,
                 project_name: str = "default"):
        self.api_key = api_key
        self.file_paths = file_paths
        self.directory_excludes = directory_excludes
        self.file_excludes = file_excludes
        self.workspace_slug = workspace_slug
        self.anythingllm_url = anythingllm_url.rstrip("/")
        self.project_name = project_name
        self.state_directory = CONFIG_DIR if project_name == "default" else CONFIG_DIR / "projects" / project_name

    @staticmethod
    def load_config(project: str | None = None):
        if os.path.exists(CONFIG_DIR / CONFIG_FILE):
            with open(CONFIG_DIR / CONFIG_FILE, "r") as f:
                config = yaml.safe_load(f)

        else:
            raise FileNotFoundError(str(CONFIG_DIR) + "/" + CONFIG_FILE + " file not found")

        if "projects" in config:
            projects = config["projects"]
            if project is None:
                if len(projects) == 1:
                    project = next(iter(projects))
                else:
                    raise KeyError("A project name is required when multiple projects are configured")
            if project not in projects:
                raise KeyError(f"Unknown project: {project}")
            project_config = {**config, **projects[project]}
            project_config.pop("projects", None)
        else:
            project = project or "default"
            project_config = config

        required = ["api-key", "file-paths", "directory-excludes", "file-excludes", "workspace-slug"]
        for key in required:
            if key not in project_config:
                raise KeyError(f"Missing configuration key: {key}")

        return AnythingLLMConfig(
            project_config["api-key"], project_config["file-paths"],
            project_config["directory-excludes"], project_config["file-excludes"],
            project_config["workspace-slug"], project_config.get("anythingllm-url", DEFAULT_URL),
            project_name=project,
        )
