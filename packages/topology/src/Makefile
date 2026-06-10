all: fxs
.PHONY: all

# Include standard NCS examples build definitions and rules
include $(NCS_DIR)/src/ncs/build/include.ncs.mk

YANG = $(wildcard yang/*.yang)
SRC  = $(and $(YANG),$(notdir $(shell grep -L "belongs-to" $(YANG))))
COMMON_YANG_DIR = ../../../common-topology/yang
COMMON_YANG = $(wildcard $(COMMON_YANG_DIR)/*.yang.in)
COMMON_SUBMODULE_DIR = ../load-dir/generated-yang
COMMON_SUBMODULES = $(COMMON_YANG:$(COMMON_YANG_DIR)/%.yang.in=$(COMMON_SUBMODULE_DIR)/%.yang)
DIRS = ../load-dir $(COMMON_SUBMODULE_DIR)
FXS  = $(SRC:%.yang=../load-dir/%.fxs)

## Uncomment and patch the line below if you have a dependency to a NED
## or to other YANG files
# YANGPATH += ../../<ned-name>/src/ncsc-out/modules/yang \
# 	../../<pkt-name>/src/yang

YANGPATH   +=	yang $(COMMON_SUBMODULE_DIR)
NCSCPATH   = $(YANGPATH:%=--yangpath %)
YANGERPATH = $(YANGPATH:%=--path %)

fxs: $(DIRS) $(FXS)
.PHONY: fxs

$(DIRS):
	mkdir -p $@

$(FXS): $(COMMON_SUBMODULES)

$(COMMON_SUBMODULE_DIR)/%.yang: $(COMMON_YANG_DIR)/%.yang.in | $(COMMON_SUBMODULE_DIR)
	sed -e 's|@PARENT_MODULE@|topology|g' \
	    -e 's|@PARENT_PREFIX@|topology|g' \
	    $< > $@

../load-dir/%.fxs: yang/%.yang
	$(NCSC) `ls $*-ann.yang  > /dev/null 2>&1 && echo "-a $*-ann.yang"` \
		$(NCSCPATH) \
		-c -o $@ $<

clean:
	rm -rf $(DIRS)
.PHONY: clean
