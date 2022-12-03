import argparse
import ntpath
import os
import sqlite3
from datetime import datetime

import pandas as pd


# Get the filename from a path
def get_file_name_from_path(file_path):
    head, tail = ntpath.split(file_path)
    return tail or ntpath.basename(head)


# Move data in a dataset to start from midnight
def data_start_from_midnight(data):
    i = 0
    flag = True
    for j in range(len(data)):
        if datetime.fromisoformat(data[j][0]).hour != 0 and not flag:
            i += 1
        else:
            flag = False
        data[j] = (set_same_date(data[j][0]), data[j][1])

    _data = data[i:]
    _data.extend(data[:i])

    return _data


# Set same date for a data
def set_same_date(timestamp, year=2020, month=1, day=1):
    return datetime.fromisoformat(timestamp).replace(year, month, day).isoformat()


# Get time from a timestamp
def get_time_from_timestamp(timestamp):
    return datetime.fromisoformat(timestamp).time().isoformat()


# Add basic arguments to manage the db to a parser
def parser_add_db_args(parser):
    parser.add_argument('--db', required=True, help='sqlite3 database to write to')
    parser.add_argument('--db_reset', action='store_true', help='Reset the database')


# Add basic arguments to manage db_dir to a parser
def parser_add_db_dir_args(parser, file_end):
    db_grp = parser.add_mutually_exclusive_group(required=True)
    db_grp.add_argument('--db', nargs='+', default=[], help='sqlite3 database to write to')
    db_grp.add_argument('--db_dir', nargs='+', default=[],
                        help=f'Paths to directory where to search for DB files. File\'s name have to end with "{file_end}"')


# Add basic arguments to manage SQL timestamp to a parser
def parser_add_sql_args(parser):
    parser.add_argument('--start', type=str, help='Start timestamp, format: YYYY-MM-DD HH:MM:SS')
    parser.add_argument('--end', type=str, help='End timestamp, format: YYYY-MM-DD HH:MM:SS')


# Add basic arguments to manage matplotlib to a parser
def parser_add_matplotlib_args(parser, default_line_style='-', default_color=None):
    parser.add_argument('--no_fill', help='Do not fill the area under the line', action='store_true')
    parser.add_argument('--line_style', help='Choose a custom line style', default=default_line_style)
    parser.add_argument('--marker', help='Choose a custom marker')
    parser.add_argument('--color', help='Choose a custom color', default=default_color)
    parser.add_argument('--no_grid', help='Do not show the grid', action='store_true')


# Add basic arguments to manage time and h24
def parser_add_time_args(parser):
    time_grp = parser.add_mutually_exclusive_group()
    time_grp.add_argument('--time', action='store_true', help='Show time on x axis')
    time_grp.add_argument('--h24', action='store_true', help='Compare dbs in 24h period starting from midnight')


# Get basic default parser
def get_basic_parser(desc, file_end, default_color=None):
    parser = argparse.ArgumentParser(description=desc)
    parser_add_db_dir_args(parser, file_end)
    parser_add_sql_args(parser)
    parser_add_matplotlib_args(parser, default_color=default_color)
    parser_add_time_args(parser)
    parser_add_pandas_args(parser)

    return parser


# Add basic arguments to manage the pandas
def parser_add_pandas_args(parser):
    parser.add_argument('--grp_freq', help='Frequency to group data', default='1s')


# Get db paths for directories
def get_db_paths_from_dirs(db_dirs, file_end):
    db_paths = []
    for dir_name in db_dirs:
        for file in os.listdir(dir_name):
            if file.endswith(file_end):
                db_paths.append(os.path.join(dir_name, file))

    return db_paths


# Check db files exist
def check_db_files_exist(db_paths):
    for db_path in db_paths:
        if not os.path.isfile(db_path):
            raise FileNotFoundError(f'DB file {db_path} does not exist')


# Validate args
def validate_args(args):
    len_dbs = len(args.db)
    if len_dbs > 1 and args.time:
        raise argparse.ArgumentTypeError('Cannot use --time with more than one DB file, use --h24 instead')

    if args.h24 and len_dbs < 2:
        raise argparse.ArgumentTypeError('Cannot use --h24 with less than two DB files')


# Choose the right SQL query to execute
# "where data" should be a string with the SQL data of conditions
def choose_sql_query(start, end, fields, table, where_data=None, h24=False):
    if h24 and (start or end):
        fields_0 = f'time({fields[0]})'
    else:
        fields_0 = fields[0]

    sql_base = f'SELECT {",".join(fields)} FROM {table}'
    order_by = f'ORDER BY {fields[0]}'
    where_data = 'true' if not where_data else f' {where_data}'
    if start and end:
        start = get_time_from_timestamp(start)
        end = get_time_from_timestamp(end)
        return f'{sql_base} WHERE {where_data} AND {fields_0} BETWEEN ? AND ? {order_by}', (start, end)
    elif start:
        start = get_time_from_timestamp(start)
        return f'{sql_base} WHERE {where_data} AND {fields_0} >= ? {order_by}', (start,)
    elif end:
        end = get_time_from_timestamp(end)
        return f'{sql_base} WHERE {where_data} AND {fields_0} <= ? {order_by}', (end,)
    else:
        return f'{sql_base} WHERE {where_data} {order_by}', ()


# Get data from a db
def get_data_from_db(db_path, start, end, fields, table, where_data=None, h24=False):
    with sqlite3.connect(db_path) as conn:
        sql_query, sql_args = choose_sql_query(start, end, fields, table, where_data, h24)
        return conn.execute(sql_query, sql_args).fetchall()


# Get data frame from data
def get_data_frame_from_data(data, fields, grp_freq='1s'):
    df = pd.DataFrame(data, columns=fields)
    df[fields[0]] = pd.to_datetime(df[fields[0]])
    df = df.groupby(pd.Grouper(key=fields[0], freq=grp_freq))

    return df


# Plot data from dataset
def plot_data_from_dataset(dataset, fields, ax, time=False, no_fill=False, line_style='-', color=None, marker=None):
    plot_data = [None, dataset['df'][fields[1]]]
    if time:
        plot_data[0] = dataset['df'][fields[0]]
    else:
        plot_data[0] = range(1, len(plot_data[1]) + 1)

    ax.plot(*plot_data, label=dataset['label'], linestyle=line_style, color=color, marker=marker)
    if not no_fill:
        if color:
            ax.fill_between(*plot_data, color=color, alpha=0.3)
        else:
            ax.fill_between(*plot_data, alpha=0.3)


# Set options for fig, ax and plt
def set_fig_ax(fig, ax, title, x_label, y_label, w_title, legend=False, no_grid=False, maximize=False, plt=None):
    fig.tight_layout()
    ax.set_title(title)
    ax.set_xlabel(x_label)
    ax.set_ylabel(y_label)
    if legend:
        ax.legend()
    if not no_grid:
        ax.grid()
    if maximize and plt:
        fig_manager = plt.get_current_fig_manager()
        fig_manager.window.showMaximized()
        fig_manager.set_window_title(w_title)


# Create title for one db plot
def get_plot_title_one_db_from_dataset(dataset):
    return f'{dataset["label"]} [{dataset["first_timestamp"]} - {dataset["last_timestamp"]}]'


# Plot data from datasets
def plot_data_from_datasets(plt, w_title, datasets, fields, y_label, no_fill=False, line_style='-', color=None,
                            marker=None, no_grid=False, time=False, h24=False, date_format=None, grp_freq='1s'):
    datasets_len = len(datasets)

    # Plot the datasets
    fig, ax = plt.subplots()
    if datasets_len == 1:
        title = get_plot_title_one_db_from_dataset(datasets[0])
        legend = False
        plot_data_from_dataset(datasets[0], fields, ax, time, no_fill, line_style,
                               color, marker)
    else:
        title = None
        legend = True
        for dataset in datasets:
            plot_data_from_dataset(dataset, fields, ax, h24, no_fill, line_style,
                                   marker=marker)

    # Set options
    if time or h24:
        ax.xaxis.set_major_formatter(date_format)
        x_label = 'Time (HH:MM:SS)'
    else:
        x_label = f'Scale time (1:{grp_freq})'
    set_fig_ax(fig, ax, title, x_label, y_label, w_title, legend, no_grid, True, plt)
