# Here we use ArbinDatapath as an example
from beep.structure import ArbinDatapath
META_ = 'atest/Severson-et-al/2017-05-12_6C-50per_3_6C_CH36_Metadata.csv'
RAW_CSV = 'atest/Severson-et-al/2017-05-12_6C-50per_3_6C_CH36.csv'



datapath = ArbinDatapath.from_file(META_)

