
# coding: utf-8

# # Library explorer
# 
# This is a short notebook to explore 2dl libraries.
# 

# In[1]:

get_ipython().magic('matplotlib inline')

#import sys
#sys.path.append("/home/eric/PycharmProjects/PyFDD")
from pyfdd import Lib2dl

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import os

pd.set_option('display.max_rows', 10000)
pd.set_option('display.max_columns', 500)
pd.set_option('display.max_colwidth', -1)


# ## Import library
# 

# In[2]:

analysis_path = "/home/eric/cernbox/University/CERN-projects/Betapix/Analysis/Channeling_analysis/"
lib_path = os.path.join(analysis_path, "FDD_libraries/GaN_89Sr/ue567g54.2dl")
lib = Lib2dl(lib_path)
df = pd.DataFrame(data=lib.get_simulations_list(),
                  columns=["Spectrum number",
                           "Spectrum_description",
                           "factor",
                           "u2",
                           "sigma"])
#for entry in lib.sim_list:


# In[3]:

df


# ## Plot pattern
# 
# use the pattern number

# In[4]:

patt_number = 1


# In[5]:

get_ipython().magic('matplotlib inline')
imgmat = lib.get_simulation_patt(patt_number)
plt.figure(dpi=150)
plt.contourf(imgmat)
plt.gca().set_aspect('equal')


# In[ ]:



