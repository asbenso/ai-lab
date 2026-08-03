# AiProjects — delegates to AgenticAi/
.PHONY: help
help:
	@$(MAKE) -C AgenticAi help

%:
	@$(MAKE) -C AgenticAi $@
