import argparse
import json
import os
import sqlite3
import webbrowser
from datetime import datetime

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import utils
from jinja2 import Template, Environment, FileSystemLoader

file_end = 'Power.db'
parser = argparse.ArgumentParser(description='Plot power data from SQL')
db_grp = parser.add_mutually_exclusive_group(required=True)
db_grp.add_argument('--db', type=str, nargs='+', default=[],
                    help='SQLite DB file name ')
db_grp.add_argument('--db_dir', type=str, nargs='+', default=[],
                    help=f'Paths to directory where to search for DB files. File\'s name have to end with "{file_end}"')
parser.add_argument('--chartjs', action='store_true', help='Use charts.js')
parser.add_argument('--matplotlib', action='store_true', help='Use matplotlib')
parser.add_argument('--line_style', type=str, default='-', help='Choose a custom line style')
parser.add_argument('--no_fill', action='store_true', help='Do not fill the area under the line')
parser.add_argument('--start', type=str, help='Start date, format: YYYY-MM-DD HH:MM:SS')
parser.add_argument('--end', type=str, help='End date, format: YYYY-MM-DD HH:MM:SS')
time_grp = parser.add_mutually_exclusive_group()
time_grp.add_argument('--time', action='store_true', help='Show time on x axis')
time_grp.add_argument('--h24', action='store_true', help='Compare dbs in 24h period starting from midnight')
args = parser.parse_args()

if args.db_dir:
    for dir_name in args.db_dir:
        for file in os.listdir(dir_name):
            if file.endswith(file_end):
                args.db.append(os.path.join(dir_name, file))
else:
    for db_name in args.db:
        if not os.path.isfile(db_name):
            exit(f'File {db_name} not found')

len_dbs = len(args.db)

if len_dbs > 1 and args.time:
    raise argparse.ArgumentTypeError('Cannot use --time with more than one DB file, use --h24 instead')

if args.h24 and len_dbs < 2:
    raise argparse.ArgumentTypeError('Cannot use --h24 with less than two DB files')

if not args.chartjs and not args.matplotlib:
    print('No chart library selected, using matplotlib')
    args.matplotlib = True

fields = ['timestamp', 'power']
SQL_BASE = 'SELECT ' + ','.join(fields) + ' FROM plug_load WHERE is_valid = 1'
ORDER_BY = ' ORDER BY timestamp'
datasets = []
for db_name in args.db:
    conn = sqlite3.connect(db_name)
    cur = conn.cursor()

    if args.start and args.end:
        cur.execute(SQL_BASE + ' AND timestamp BETWEEN ? AND ?' + ORDER_BY, (args.start, args.end))
    elif args.start:
        cur.execute(SQL_BASE + ' AND timestamp >= ?' + ORDER_BY, (args.start,))
    elif args.end:
        cur.execute(SQL_BASE + ' AND timestamp <= ?' + ORDER_BY, (args.end,))
    else:
        cur.execute(SQL_BASE + ORDER_BY)

    data = cur.fetchall()
    if data:
        dataset = {
            'label': utils.file_name(db_name),
            'data': data if not args.h24 else utils.data_start_from_midnight(data),
            'first_timestamp': data[0][0],
            'last_timestamp': data[-1][0]
        }

        if args.time or args.h24:
            dataset['timestamps'] = []
        for i in range(len(dataset['data'])):
            if args.time or args.h24:
                dataset['timestamps'].append(dataset['data'][i][0])

            dataset['data'][i] = dataset['data'][i][1]

        datasets.append(dataset)
    else:
        print(f'No data found in {db_name}')
    conn.close()

datasets_len = len(datasets)
max_number_of_rows = max([len(dataset['data']) for dataset in datasets])

if args.chartjs:
    env = Environment(loader=FileSystemLoader('.'))
    template = env.get_template('chartjs_template.html')

    with open('chartjs.html', 'w') as f:
        chart_datasets = []
        for dataset in datasets:
            chart_datasets.append({
                'label': dataset['label'],
                'data': dataset['data'],
                'fill': True if datasets_len > 1 else False,
            })

        f.write(template.render(labels=range(1, max_number_of_rows + 1),
                                datasets=json.dumps(chart_datasets)))

    webbrowser.open('file://' + os.path.realpath('chartjs.html'))

if args.matplotlib:
    if datasets_len == 1:
        plot_data = [None, datasets[0]['data']]
        if args.time:
            plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
            plot_data[0] = [datetime.fromisoformat(t) for t in datasets[0]['timestamps']]
            plt.xlabel('Time (HH:MM:SS)')
        else:
            plot_data[0] = range(1, max_number_of_rows + 1)

        plt.title(
            f'Plug Power from {utils.file_name(args.db[0])} [{datetime.fromisoformat(datasets[0]["first_timestamp"])} - {datetime.fromisoformat(datasets[0]["last_timestamp"])}] (UTC)')
        plt.plot(*plot_data, args.line_style)
        if not args.no_fill:
            plt.fill_between(*plot_data, alpha=0.3)

    else:
        for dataset in datasets:
            plot_data = [None, dataset['data']]
            if args.h24:
                plot_data[0] = [datetime.fromisoformat(utils.set_same_date(t)) for t in dataset['timestamps']]
                plt.plot(*plot_data, label=dataset['label'], alpha=0.6)
            else:
                plot_data[0] = range(1, len(plot_data[1]) + 1)
                plt.plot(*plot_data, args.line_style, label=dataset['label'])
                if not args.no_fill:
                    plt.fill_between(*plot_data, alpha=0.3)

        if args.h24:
            plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
            plt.xlabel('Time (HH:MM:SS)')
        else:
            plt.xlabel('Seconds since capture')
        plt.legend()

    plt.ylabel('Power (W)')
    plt.grid()
    plt.show()
