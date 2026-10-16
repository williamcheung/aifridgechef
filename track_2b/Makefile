.PHONY: run stop

# Directory of this Makefile, so `make run` works whether invoked from this
# directory (cd track_2b && make run) or from elsewhere (make -C track_2b run).
MKFILE_DIR  := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))

# --- Configuration ---
IMAGE       := aifridgechef
CONTAINER   := aifridgechef
# Gradio UI port (app listens on 0.0.0.0:7860)
PORT        := 7860
# Docker build context (contains the Dockerfile)
SRC_DIR     := $(MKFILE_DIR)/src
ENV_FILE    := $(SRC_DIR)/.env

# Build the Docker image and run the container.
# The .env file is baked into the image at build time (Dockerfile COPY), so it
# must exist BEFORE building. Create it from the sample and fill in real values:
#     cp src/.env_sample src/.env            # bash
#     Copy-Item src/.env_sample src/.env     # Windows PowerShell
run:
	@test -f "$(ENV_FILE)" || { \
		echo "ERROR: $(ENV_FILE) not found."; \
		echo "Create it first:  cp src/.env_sample src/.env  (in the track_2b directory) and fill in the values."; \
		exit 1; \
	}
	docker build -t $(IMAGE) "$(SRC_DIR)"
	-docker rm -f $(CONTAINER) 2>/dev/null || true
	docker run --rm --name $(CONTAINER) -p $(PORT):$(PORT) $(IMAGE)
	@echo "App running at http://localhost:$(PORT)"

# Stop the running container (if any).
stop:
	-docker rm -f $(CONTAINER) 2>/dev/null || true
