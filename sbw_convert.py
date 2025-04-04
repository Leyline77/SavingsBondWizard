# Read and convert sbw files - tested on sbw v4
import struct
import os
from datetime import datetime
from dateutil.relativedelta import relativedelta
import json
import csv
from io import StringIO
import argparse

# Constants and error codes
SBW4_CBOND_SIZE = 5
SBW4_EPOCH = datetime(1941, 4, 1)

GB_ERROR_OPEN_SBW_CANNOT_OPEN_FILE = 1
GB_ERROR_OPEN_SBW_BAD_MAGIC = 2
GB_ERROR_OPEN_SBW_PARSE = 3
GB_OK = 0

# Class Definitions
class GBStatus:
    def __init__(self):
        self.code = GB_OK

class GBDocBond:
    def __init__(self, series, idate, denom, sn):
        self.series = series
        self.idate = idate
        self.denom = denom
        self.sn = sn

class GBDoc:
    def __init__(self):
        self.title = ""
        self.bonds = []

    def set_title(self, title):
        self.title = title

    def add_bond(self, bond):
        self.bonds.append(bond)

    def to_json(self, pretty=False):
        data = {
            "title": self.title,
            "bonds": [
                {
                    "series": bond.series,
                    "issue_date": bond.idate,
                    "denomination": bond.denom,
                    "serial_number": bond.sn,
                }
                for bond in self.bonds
            ],
        }
        if pretty:
            return json.dumps(data, indent=2)
        return json.dumps(data)

    def to_csv(self, include_header=True):
        output = StringIO()
        writer = csv.writer(output)

        if include_header:
            writer.writerow(["Series", "Denomination", "Serial Number", "Issue Date"])

        for bond in self.bonds:
            writer.writerow([
                bond.series,
                bond.denom,
                bond.sn,
                bond.idate
            ])

        return output.getvalue()

    def to_csv_file(self, filename, include_header=True):
        """Writes bond data to a CSV file."""
        with open(filename, mode="w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)

            if include_header:
                writer.writerow(["Series", "Denomination", "Serial Number", "Issue Date"])

            for bond in self.bonds:
                writer.writerow([
                    bond.series,
                    bond.denom,
                    bond.sn,
                    bond.idate,

                ])

        print(f"CSV file saved as: {filename}")

# Definitions
def gb_doc_new():
    return GBDoc()

def gb_doc_bond_new(series, idate, denom, sn, status):
    try:
        return GBDocBond(series, idate, float(denom), sn)
    except Exception:
        status.code = GB_ERROR_OPEN_SBW_PARSE
        return None

def gb_date_fmt(months_since_epoch):
    date = SBW4_EPOCH + relativedelta(months=months_since_epoch)
    return date.strftime('%m/%Y')

def read_sbw2(fp, status):
    doc = gb_doc_new()
    status.code = GB_OK

    version_line = fp.readline().strip()
    if version_line not in [b'"SBW 2"', b'"SBW 3"']:
        status.code = GB_ERROR_OPEN_SBW_BAD_MAGIC
        return None

    title_line = fp.readline().decode('utf-8').strip().strip('"')
    doc.set_title(title_line)

    fp.readline()  # skip redemption date
    try:
        n = int(fp.readline().decode('utf-8').strip())
    except ValueError:
        status.code = GB_ERROR_OPEN_SBW_PARSE
        return None

    for _ in range(n):
        line = fp.readline().decode('utf-8')
        fields = line.split(",", 4)
        if len(fields) < 4:
            continue
        sn = fields[0].strip().strip('"')
        denom = fields[1].strip().strip('"')
        series = fields[2].strip().strip('"')
        idate = fields[3].strip().strip('"')

        bond = gb_doc_bond_new(series, idate, denom, sn, status)
        if status.code != GB_OK:
            return None
        doc.add_bond(bond)

    return doc

def read_sbw4(fp, status):
    doc = gb_doc_new()
    doc.set_title("Imported SBW4 Inventory")
    status.code = GB_OK

    head_raw = fp.read(12)
    if len(head_raw) < 12:
        status.code = GB_ERROR_OPEN_SBW_PARSE
        return None

    rdate, _, n_bonds, *_ = struct.unpack('<HHHHHH', head_raw)

    cbond = fp.read(SBW4_CBOND_SIZE)

    for i in range(n_bonds):
        bond_data = fp.read(84)  # 21 * 4 bytes
        if len(bond_data) < 84:
            status.code = GB_ERROR_OPEN_SBW_PARSE
            return None

        unpacked = struct.unpack('<' + 'I' * 21, bond_data)
        denom = unpacked[6]
        idate = unpacked[10]

        # Read notes (ignore contents)
        n_bytes = struct.unpack('<B', fp.read(1))[0]
        if n_bytes > 0:
            fp.read(n_bytes)

        # Serial number
        sn = ""
        n_bytes = struct.unpack('<B', fp.read(1))[0]
        if n_bytes > 0:
            sn = fp.read(n_bytes).decode('utf-8')

        # Series
        series = ""
        n_bytes = struct.unpack('<B', fp.read(1))[0]
        if n_bytes > 0:
            series = fp.read(n_bytes).decode('utf-8')

        if i < n_bonds - 1:
            fp.read(2)  # inter-record short

        if series.upper() in ["E", "S", "EE", "I"]:
            idate_string = gb_date_fmt(idate)
            bond = gb_doc_bond_new(series, idate_string, denom, sn, status)
            if status.code != GB_OK:
                return None
            doc.add_bond(bond)

    return doc

def export_sbw_to_json(filename, pretty=False):
    status = GBStatus()
    doc = gb_doc_sbw_open(filename, status)

    if status.code != GB_OK or doc is None:
        print(f"Failed to parse file. Error code: {status.code}")
        return

    json_output = doc.to_json(pretty=pretty)
    print(json_output)

def export_sbw_to_csv(filename, outFile=""):
    status = GBStatus()
    doc = gb_doc_sbw_open(filename, status)

    if status.code != GB_OK or doc is None:
        print(f"Failed to parse file. Error code: {status.code}")
        return

    if outFile:
        print("CSV file write, to display on screen leave outFile blank.")
        doc.to_csv_file(outFile)
    else:
        print("CSV Display Output, pass a filename to write file.")
        csv_output = doc.to_csv()
        print(csv_output)


def gb_doc_sbw_open(filename, status):
    if not os.path.isfile(filename):
        status.code = GB_ERROR_OPEN_SBW_CANNOT_OPEN_FILE
        return None

    with open(filename, 'rb') as fp:
        first_line = fp.readline()
        fp.seek(0)

        version = 0
        if first_line.startswith(b'"SBW 2"') or first_line.startswith(b'"SBW 3"'):
            version = 2
        else:
            fp.seek(12)
            cbond = fp.read(SBW4_CBOND_SIZE)
            if cbond.startswith(b'CBond'):
                version = 4
            fp.seek(0)

        if version == 2:
            return read_sbw2(fp, status)
        elif version == 4:
            return read_sbw4(fp, status)
        else:
            status.code = GB_ERROR_OPEN_SBW_BAD_MAGIC
            return None


def main():
    # Setup argparse to handle command line arguments
    parser = argparse.ArgumentParser(description="Import SBW data and export it as JSON or CSV.")
    parser.add_argument('sbw_file', type=str, help="Path to the SBW file to import.")
    parser.add_argument('csv_file', nargs='?', type=str, help="Optional path to save the CSV file.")
    parser.add_argument('--csv', action='store_true', help="Flag to export to CSV.")
    parser.add_argument('--pretty', action='store_true', help="Flag to output JSON in a pretty format.")
    
    args = parser.parse_args()

    if args.csv or args.csv_file:
        # Export to CSV if --csv flag or csv_file is provided
        export_sbw_to_csv(args.sbw_file, args.csv_file)
    else:
        # Export to JSON by default
        json_output = export_sbw_to_json(args.sbw_file, pretty=args.pretty)
        print(json_output)


if __name__ == "__main__":
    main()

exit()

# Example usage
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python sbw_importer.py <sbw_file> [csv_file] [--csv] [--pretty]")
    else:
        fname = sys.argv[1]
        pretty = "--pretty" in sys.argv
        export_sbw_to_json(fname, pretty=pretty)

    #if csv
        export_sbw_to_csv(sbw_file, csv_file)

# Dev Use - hardcode options
sbw_file = "savings_bonds.sbw"
csv_file = "savings_bonds.csv"

#for JSON
pretty = "--pretty"

csv_file = "" # Blank for display only
# export_sbw_to_json(sbw_file, pretty=pretty)
export_sbw_to_csv(sbw_file, csv_file)

print(f"Conversion complete. Data shown as JSON.")

