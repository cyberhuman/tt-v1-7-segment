# Prepare the gate level netlist and an SDF file for Icarus Verilog.
# usage: sdf_prepare.py NETLIST.v IN.sdf OUT_NETLIST.v OUT.sdf
#
# Icarus reads SDF instance names as hierarchy paths, so the escaped flat
# names of the hardened netlist (digit0.mux1.u, clkbuf_0_ui_in[2]) are renamed
# in both files: every character that is not a letter, digit or underscore
# becomes "_". The INTERCONNECT lines are dropped: Icarus cannot annotate a
# net that is a bit of a bus (ui_in[2]). The cell delays (IOPATH) are kept.
import re
import sys

netlist, sdf, out_netlist, out_sdf = sys.argv[1:5]


def clean(name):
    return re.sub(r"[^A-Za-z0-9_]", "_", name)


text = open(netlist).read()
text = re.sub(r"\\(\S+)", lambda m: clean(m.group(1)), text)
open(out_netlist, "w").write(text)

lines = []
for line in open(sdf):
    if "INTERCONNECT" in line:
        continue
    if "(INSTANCE" in line:
        line = re.sub(r"\(INSTANCE\s+(\S+?)\)",
                      lambda m: "(INSTANCE " + clean(m.group(1).replace("\\", "")) + ")",
                      line)
    lines.append(line)
# the top cell held only INTERCONNECT lines: an empty ABSOLUTE is a syntax error
body = re.sub(r"\(DELAY\s*\(ABSOLUTE\s*\)\s*\)", "", "".join(lines))
open(out_sdf, "w").write(body)
