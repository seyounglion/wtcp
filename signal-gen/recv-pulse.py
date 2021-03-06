import sys
from math import *
import numpy
import matplotlib.pyplot as p
from matplotlib.pyplot import *
import scipy.cluster as cluster
from Filter import *
from scipy.signal import kaiserord, lfilter, firwin, freqz
import wave
import struct 
def read_from_file(w,channel,start_time,end_time,sample_rate) : 
     ''' File handling routines 
     '''
     stream=[]
     upper_limit=int(end_time*sample_rate);
     if(upper_limit>w.getnframes()):
        upper_limit=w.getnframes();
     lower_limit=int(start_time*sample_rate);

     # seek to lower_limit
     # find byte position of lower_limit
     w.setpos(lower_limit)
     i=1
     while (i<=(upper_limit-lower_limit)) :
         frame = w.readframes(1)
         if(channel==1) :
           value=struct.unpack("<h",frame[0:2])[0]
         if(channel==2) :
           value=struct.unpack("<h",frame[2:4])[0]
         stream.append(value/32768.0);
         i=i+1
     print >> sys.stderr, "At End time",end_time," in channel ",channel
     return numpy.array(stream)

def low_pass_filter(cutoff,width,sample_rate) : 
    ''' 
        Get low pass filter kernel  for cutoff freq in Hz width in Hz
        Borrowed from http://www.scipy.org/Cookbook/FIRFilter '''
    nyq_rate = sample_rate / 2.0
    width = width/nyq_rate # normalize to Nyq Rate 
    ripple_db = 30.0 # 60 dB attenuation in the stop band
    # Compute the order and Kaiser parameter for the FIR filter.
    N,beta = kaiserord(ripple_db, width)
    cutoff=cutoff/nyq_rate
    taps = firwin(N, cutoff, window=('kaiser', beta))
    return taps

def run_low_pass(stream,kernel) : 
    filtered_signal=lfilter(kernel,1.0,stream);  
    # phase delay
    delay_in_samples = int(0.5 * (len(kernel)-1)) ;
    # "pull back" the delayed signal
    # ie start returning the signal from the delay_in_samples^{th} signal onwards as the correct signal. Pad enough zeros at the end to make it the same size.
    return numpy.concatenate((filtered_signal[delay_in_samples:],numpy.array([0]*delay_in_samples)))

def cos_memoize(centre_freq,length,sample_rate) :
     if centre_freq in cos_memoize.stored_samples :
          current_length=len(cos_memoize.stored_samples[centre_freq]);
          if(length<=current_length) :
              return cos_memoize.stored_samples[centre_freq][0:length];
          else :
              nvalues=range(current_length,length);
              cos_memoize.stored_samples[centre_freq]=numpy.concatenate((cos_memoize.stored_samples[centre_freq][0:current_length],numpy.cos( ((2* numpy.pi * centre_freq)/sample_rate) * numpy.array(nvalues))))
              return cos_memoize.stored_samples[centre_freq][0:length];
     else : 
          current_length=0;
          nvalues=range(current_length,length);
          cos_memoize.stored_samples[centre_freq]=numpy.cos( ((2* numpy.pi * centre_freq)/sample_rate) * numpy.array(nvalues))
          return cos_memoize.stored_samples[centre_freq][0:length];
cos_memoize.stored_samples=dict()

def sin_memoize(centre_freq,length,sample_rate) :
     if centre_freq in sin_memoize.stored_samples :
          current_length=len(sin_memoize.stored_samples[centre_freq]);
          if(length<=current_length) :
              return sin_memoize.stored_samples[centre_freq][0:length];
          else :
              sin_memoize.stored_samples[centre_freq]=numpy.concatenate((sin_memoize.stored_samples[centre_freq][0:current_length],numpy.sin( ((2* numpy.pi * centre_freq)/sample_rate) * numpy.arange(current_length,length))))
              return sin_memoize.stored_samples[centre_freq][0:length];
     else : 
          current_length=0;
          sin_memoize.stored_samples[centre_freq]=numpy.sin( ((2* numpy.pi * centre_freq)/sample_rate) * numpy.arange(current_length,length))
          return sin_memoize.stored_samples[centre_freq][0:length];
sin_memoize.stored_samples=dict()

def quad_demod(stream,centre_freq,bandwidth,sample_rate,amplitude) :
      ''' 
          quadrature demodulation of received signal 
      '''
      stream_length=len(stream); 
#      nvalues=range(0,stream_length);
      
      # lpf common to I and Q
      lpf=low_pass_filter(50.0,50.0,sample_rate);
      # modulate with cosine and lpf it
      cosine=cos_memoize(centre_freq,stream_length,sample_rate);
      i_stream=cosine*stream ;
      i_stream_lpf=run_low_pass(i_stream,lpf);

      # modulate with sine and lpf it
      sine=sin_memoize(centre_freq,stream_length,sample_rate);
      q_stream=sine*stream ;
      q_stream_lpf=run_low_pass(q_stream,lpf); 

      # get the absolute value  
      abs_stream=numpy.sqrt(i_stream_lpf*i_stream_lpf + q_stream_lpf*q_stream_lpf);

      # find slicing threshold for peak detector. 
      slice_threshold=(amplitude/4); # / 2 for the original 1/2 while squaring, Another /2 for detecting the crossing. 
#      print "Slice threshold is",slice_threshold
      # slice the signal 
      slice_stream=(abs_stream>slice_threshold)*1;
      # find start of pulse 
      # plot slice_stream 
      ##subplot(211)
      ##p.plot(slice_stream);
 
      ### plot abs_stream
      ##subplot(212)
      ## p.figure()
      ## p.plot(abs_stream);
      ## p.plot(numpy.array([slice_threshold]*len(abs_stream)));
      ## p.draw()
      # show it now 
      a=numpy.nonzero(slice_stream)
      while(len(a[0])==0) :
          # keep reducing the slice threshold till something clicks 
          print>>sys.stderr,"Failed to find a point crossing the threshold, 0.75* the threshold and retrying"
          slice_threshold=slice_threshold*0.75;
          for i in range(0,len(slice_stream)): 
             slice_stream[i]=1 if (abs_stream[i]>slice_threshold) else 0;
          a=numpy.nonzero(slice_stream)
      return a[0][0]

# Now the main routine
def get_sender_schedule(freq_file_fh) : 
   schedule=[]
   for line in freq_file_fh.readlines() : 
       if(len(line.split()) == 4) :
         schedule.append(0);
       else :
         freq=float(line.split()[5]);
         schedule.append(freq);  
   return schedule


def search_for_freq(stream,start_time,frequency,sample_rate,amplitude) : 
    lower_limit=int(start_time*sample_rate);
    start_index=quad_demod(stream,frequency,0,sample_rate,amplitude);
    start_time=float(lower_limit+start_index+1)/float(sample_rate)
    return start_time

# main function  
if(len(sys.argv) < 8) : 
    print "Usage : python recv-pulse.py filename freq_file sample_rate pulse_width batch_separation amplitude channel"
    exit(5)

file_name=sys.argv[1];
freq_file_fh=open(sys.argv[2],'r');
sample_rate=float(sys.argv[3]); 
pulse_width=float(sys.argv[4]);
batch_separation=float(sys.argv[5]);
amplitude=float(sys.argv[6]);
channel=int(sys.argv[7]);
schedule=get_sender_schedule(freq_file_fh);
w = wave.open(file_name, 'r')

# retrieve the stream based on what you sent 
locations=[0]*len(schedule)
for i in range(0,len(schedule)) :
    if (i==0) : 
      # search 1.5 seconds for the first frequency pulse 
      start_time=0
      end_time=1.5     
    else :
      start_time=locations[i-1]+pulse_width/2; # half way to the end of this pulse 
      end_time=locations[i-1]+3*pulse_width/2; # half way after the pulse you are looking for 

    if(schedule[i]!=0) : # not silence
      stream=read_from_file(w,channel,start_time,end_time,sample_rate) ;
      locations[i]=search_for_freq(stream,start_time,schedule[i],sample_rate,amplitude) 
    else :  # if it is silence 
      locations[i]=locations[i-1] + batch_separation ; # in effect, "skip" the silence
print locations
