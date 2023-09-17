'''
Import-able class for communication and live plotting over USB serial.
'''
import time
import tkinter as tk
from tkinter import ttk
from tkinter import filedialog
import serial
import pandas as pd
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt
plt.style.use('bmh')

class SimpleDAQ:
    '''
    Contains all methods required to send/receive data over USB serial.
    '''
    def __init__(self, mc_data_dict, update_delay_seconds=1):
        self.log = []
        self.pressure_data = []
        self.time_data = []
        self.start_time = time.time()
        self.mc_data_dict = mc_data_dict
        self.update_delay_seconds = update_delay_seconds
        self.ser = serial.Serial('COM6', 115200)
        self.datafilepath, self.logfilepath = None, None
        self._define_save_files()
        self._start_gui()

    def _start_gui(self):
        # Initialize Tkinter root window
        self.root = tk.Tk()
        self.root.title("Data Logging GUI")

        # Matplotlib Figure
        self.fig = Figure(figsize=(6, 4), dpi=175)
        self.ax = self.fig.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.root)
        self.canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=1)

        # Exit button
        ttk.Button(self.root, text="Exit", command=self._exit_program).pack()

        if self.datafilepath:
            self.root.after(self.update_delay_seconds*1000, self._update)
            self.root.mainloop()

    def _define_save_files(self):
        self.datafilepath = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files", "*.csv")])
        self.logfilepath = self.datafilepath.replace('.csv', '_log.txt')
        if self.datafilepath:
            self.log.append(f"Program started at {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}")
            with open(self.logfilepath, 'w', encoding='utf8') as f:
                for entry in self.log:
                    f.write(f"{entry}\n")
            self.log.append(f"Data will be saved to {self.datafilepath}")

    def _update(self):
        ser_data = self.ser.readline().decode('utf-8').strip()
        run_duration = time.time() - self.start_time
        self.pressure_data.append(float(ser_data))
        self.time_data.append(run_duration)
        self.ax.clear()
        self.ax.set_title('Data Acquisition')
        self.ax.set_xlabel('Time (s)')
        self.ax.set_ylabel('Sensor Data')
        self.ax.minorticks_on()
        self.ax.plot(self.time_data, self.pressure_data)
        self.ax.grid(True, which='major', color='silver', linewidth=0.375, linestyle='-')
        self.ax.grid(True, which='minor', color='lightgrey', linewidth=0.2, linestyle='--')
        self.canvas.draw()

        if run_duration % 10 < 1:  # Save every 10 seconds
            df = pd.DataFrame({"Time": self.time_data, "Pressure": self.pressure_data})
            df.to_csv(self.datafilepath, index=False)
            with open(self.logfilepath, 'w', encoding='utf8') as f:
                for entry in self.log:
                    f.write(f"{entry}\n")

        self.root.after(1000*self.update_delay_seconds, self._update)

    def _user_input(self, inputdata):
        self.log.append(f"User input at {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}: {inputdata}")

    def _exit_program(self):
        self.log.append(f"Program exited at {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))}")
        with open(self.logfilepath, 'w', encoding='utf8') as f:
            for entry in self.log:
                f.write(f"{entry}\n")
        self.ser.close()
        self.root.quit()
        self.root.destroy()

if __name__ == '__main__':
    sdaq = SimpleDAQ({},1)
