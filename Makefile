.SUFFIXES:

IMAGE_NAME = nso-topology-manager
CNT_NAME = $(IMAGE_NAME)

nso_install_file = $(wildcard nso-install-file/nso-*.linux.x86_64.installer.bin)

docker-build:
	@if [ $(words $(nso_install_file)) -ne 1 ]; then \
	  echo "Unable to find NSO installer binary"; \
	  exit 1; \
	fi
	docker build --build-arg NSO_INSTALL_FILE=$(nso_install_file) --progress=plain --target nso-build -t $(IMAGE_NAME) .

docker-start: docker-run docker-wait-started

docker-stop:
	@docker logs -f --since 0m $(CNT_NAME) &
	docker stop --time 60 $(CNT_NAME)
	docker rm $(CNT_NAME)

docker-shell:
	docker exec -it $(CNT_NAME) bash -l


docker-run:
	docker run --name $(CNT_NAME) -td $(IMAGE_NAME)

docker-wait-started:
	@docker logs -f $(CNT_NAME) & LOGS_PID="$$!"; \
	while ! docker logs $(CNT_NAME) | grep -q "run-nso.sh: startup complete"; do \
	  sleep 10; \
	done; \
	kill $${LOGS_PID}

.PHONY: docker-build docker-start docker-stop docker-shell docker-run docker-wait-started
