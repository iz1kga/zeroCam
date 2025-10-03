import os
import json
import datetime
from collections import deque

import pandas as pd

from lib.helpers import get_raspberry_pi_stats

class StatsCollector:
    """Collects, aggregates, and persists hardware statistics."""

    def __init__(self, logger, history_file='/usr/local/zerocam/app/logs/stats.json', maxlen=288):
        self.logger = logger
        self.history_length = maxlen
        self.stats_history = deque(maxlen=maxlen)
        self.stats_buffer = []
        self.history_file = history_file
        self._load_stats_from_disk()

    def _load_stats_from_disk(self):
        """Loads historical stats from a file on startup."""
        try:
            if os.path.exists(self.history_file):
                with open(self.history_file, 'r') as f:
                    for line in f:
                        try:
                            self.stats_history.append(json.loads(line.strip()))
                        except json.JSONDecodeError:
                            continue
                self.logger.info(f"Loaded {len(self.stats_history)} historical stats records.")
        except IOError as e:
            self.logger.error(f"Error reading stats history file: {e}")

    def _write_stats_to_disk(self, record):
    """
    Appends a new aggregated stat record to the history file.
    Ensures the file does not exceed self.history_length lines by removing the oldest records.
    """
    try:
        lines = []
        if os.path.exists(self.history_file):
            with open(self.history_file, 'r') as f:
                lines = f.readlines()
                
        lines.append(json.dumps(record) + '\n')

        if len(lines) > self.history_length:
            lines = lines[-self.history_length:]

        with open(self.history_file, 'w') as f:
            f.writelines(lines)

    except IOError as e:
        self.logger.error(f"Error writing to stats history file: {e}")

    def collect_and_process(self):
        """Collects current stats and processes the buffer if it's large enough."""
        try:
            stats = get_raspberry_pi_stats()
            stats['timestamp'] = datetime.datetime.now().timestamp()
            self.stats_buffer.append(stats)
            self.logger.debug(f"Collected stats, buffer size: {len(self.stats_buffer)}")

            # Aggregate when buffer is full or for the first time
            if len(self.stats_buffer) >= 300 or (len(self.stats_buffer) > 1 and not self.stats_history):
                df = pd.DataFrame(self.stats_buffer)
                result = {
                    'cpuTemperature': {'min': df['cpuTemperature'].min(), 'max': df['cpuTemperature'].max(), 'average': df['cpuTemperature'].mean()},
                    'cpuUsage': {'min': df['cpuUsage'].min(), 'max': df['cpuUsage'].max(), 'average': df['cpuUsage'].mean()},
                    'memoryUsage': {'min': df['memoryUsage'].min(), 'max': df['memoryUsage'].max(), 'average': df['memoryUsage'].mean()},
                    'diskUsage': {'min': df['diskUsage'].min(), 'max': df['diskUsage'].max(), 'average': df['diskUsage'].mean()},
                    'loadAverage': self.stats_buffer[-1].get('loadAverage'),
                    'timestamp': self.stats_buffer[-1].get('timestamp')
                }
                
                self.stats_history.append(result)
                self._write_stats_to_disk(result)
                # Keep the last measurement to ensure no data is lost
                self.stats_buffer = self.stats_buffer[-1:]
        except Exception as e:
            self.logger.error(f"Error during stats collection: {e}", exc_info=True)