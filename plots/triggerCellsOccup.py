import os
import random
import argparse
import numpy as np
import pandas as pd
import uproot as up

from bokeh.io import output_file, show
from bokeh.layouts import gridplot
from bokeh.models import (BasicTicker, ColorBar, ColumnDataSource,
                          LogColorMapper, LogTicker,
                          LinearColorMapper, BasicTicker,
                          PrintfTickFormatter,
                          Range1d,
                          Panel, Tabs)
from bokeh.plotting import figure
from bokeh.sampledata.unemployment1948 import data as testdata
from bokeh.transform import transform
from bokeh.palettes import viridis as _palette

def calculateRoverZfromEta(eta):
    """R/z = arctan(theta) [theta is obtained from pseudo-rapidity, eta]"""
    _theta = 2*np.arctan( np.exp(-1 * eta) )
    return np.arctan( _theta )

def convertToBinIndex(val, binedges):
    """
    Converts any value into a "bin index". It is based on bin edges coming from a binned
    distribution of the same value. This "index" is a decimal number.
    Example: 
        data = [1,2,3,4] is binned with binedges=[1,3,5] 
        (two bins with bin indexes = [0,1])
        ...
        convertToBinIndex(0, binedges) throws AssertionError
        convertToBinIndex(1, binedges)=0.0
        convertToBinIndex(2, binedges)=0.5
        convertToBinIndex(3, binedges)=1.0
        convertToBinIndex(4, binedges)=1.5
        convertToBinIndex(5, binedges) throws AssertionError
        ...
    Useful when plotting a continuous variable over a binned distribution.
    We assume the first bin index to be zero (like in pandas.cut).
    """
    assert( val >= binedges[0] and val <= binedges[-1] )
    fraction = (val-binedges[0]) / (binedges[-1]-binedges[0]) #]0;1[

    minbinedge = 0. #from pandas.cut() with labels=False
    maxbinedge = float(len(binedges)-1) #shift one unit because the indexes start from zero
    conv_val = minbinedge + (maxbinedge-minbinedge)*fraction #float
    return conv_val

class dotDict(dict):
    """dot.notation access to dictionary attributes"""
    __getattr__ = dict.get
    __setattr__ = dict.__setitem__
    __delattr__ = dict.__delitem__

def set_figure_props(p, xbincenters, ybincenters):
    """set figure properties"""
    p.axis.axis_line_color = 'black'
    p.axis.major_tick_line_color = 'black'
    p.axis.major_label_text_font_size = '10px'
    p.axis.major_label_standoff = 2
    #p.xaxis.major_label_orientation = 1.0
    p.xaxis.axis_label = r"$$\color{black} \phi$$"
    p.xaxis.major_label_overrides = {dig: label for dig,label in enumerate(xbincenters)}
    p.yaxis.axis_label = '$$R/z$$'
    p.yaxis.major_label_overrides = {dig: label for dig,label in enumerate(ybincenters)}
    
    p.hover.tooltips = [
        ("#hits", "@{nhits}"),
        ("min(eta)", "@{min_eta}"),
        ("max(eta)", "@{max_eta}"),
    ]

parser = argparse.ArgumentParser(description='Plot trigger cells occupancy.')
parser.add_argument('--nphibins', help='number of uniform phi bins',
                    default=216, type=int)
parser.add_argument('--nrzbins', help='number of uniform R/z bins',
                    default=42, type=int)
parser.add_argument('--nevents', help='number of events to display',
                    default=8, type=int)
parser.add_argument('-z', '--pos_endcap', help='Use only the positive endcap.',
                    default=True, type=bool)
parser.add_argument('--minROverZ', help='Minimum value of R/z, as defined in CMSSW.',
                    default=0.076, type=float)
parser.add_argument('--maxROverZ', help='Maximum value of R/z, as defined in CMSSW.',
                    default=0.58, type=float)
parser.add_argument('--mode', help='Trigger cells or simulation.',
                    required=True, choices=['tc', 'sim'], default=0.58, type=str)
parser.add_argument('-d', '--debug', help='debug mode', action='store_true')
parser.add_argument('-l', '--log', help='use color log scale', action='store_true')

FLAGS = parser.parse_args()

#########################################################################
################### CONFIGURATION PARAMETERS ############################
#########################################################################
NEVENTS = FLAGS.nevents
NBINSRZ = FLAGS.nrzbins
NBINSPHI = FLAGS.nphibins

rzBinEdges = np.linspace( FLAGS.minROverZ, FLAGS.maxROverZ, num=NBINSRZ )
rzBinCenters = ['{:.2f}'.format(x) for x in ( rzBinEdges[1:] + rzBinEdges[:-1] ) / 2 ]
phiBinEdges = np.linspace( -np.pi, np.pi, num=NBINSPHI )
phiBinCenters = ['{:.2f}'.format(x) for x in ( phiBinEdges[1:] + phiBinEdges[:-1] ) / 2 ]

SHIFTH, SHIFTV = 1, 1
BINWIDTH=1

tcDataPath = os.path.join(os.environ['HOME'], 'Downloads', 'test_triggergeom.root')
tcFile = up.open(tcDataPath)
tcFolder = 'hgcaltriggergeomtester'
tcTreeName = 'TreeTriggerCells'
tcTree = tcFile[ os.path.join(tcFolder, tcTreeName) ]
if FLAGS.debug:
    print('Input Tree:')
    print(tcTree.show())
        
simDataPath = os.path.join(os.environ['PWD'], 'data', 'gen_cl3d_tc.hdf5')
simAlgoDFs, simAlgoFiles, simAlgoPlots = ({} for _ in range(3))
fes = ['Threshold']
for fe in fes:
    simAlgoFiles[fe] = [ os.path.join(simDataPath) ]

title_common = r'Mode: {} ({} vs {} bins)'.format(FLAGS.mode, NBINSPHI, NBINSRZ)
if FLAGS.pos_endcap:
    title_common += '; Positive end-cap only'
title_common += '; Min(R/z)={} and Max(R/z)={}'.format(FLAGS.minROverZ, FLAGS.maxROverZ)

mypalette = _palette(40)
#########################################################################
################### INPUTS: TRIGGER CELLS ###############################
#########################################################################
tcNames = dotDict( dict( RoverZ = 'Rz',
                         phi_calc = 'phi_calc',
                         phi = 'phi',
                         eta = 'eta',
                         nhits = 'nhits',
                         min_eta = 'min_eta',
                         max_eta = 'max_eta',
                        )
                  )

tcVariables = {'zside', 'subdet', 'layer', tcNames.phi, tcNames.eta, 'x', 'y', 'z'}
assert(tcVariables.issubset(tcTree.keys()))
tcVariables = list(tcVariables)

tcData = tcTree.arrays(tcVariables, library='pd')
if FLAGS.debug:
    print( tcData.describe() )
    
#########################################################################
################### INPUTS: SIMULATION 0 PU PHOTONS #####################
#########################################################################
simNames = dotDict( dict( RoverZ = 'Rz',
                          etatc = 'tc_eta',
                          phitc = 'tc_phi',
                          entc  = 'tc_mipPt',
                          nhits = 'nhits',
                          eta3d = 'cl3d_eta',
                          phi3d = 'cl3d_phi',
                          etagen = 'genpart_exeta',
                          phigen = 'genpart_exphi',

                          min_eta = 'min_eta',
                          max_eta = 'max_eta',
                          sum_en =  'sum_en',
                         ) )

for fe,files in simAlgoFiles.items():
    name = fe
    dfs = []
    for file in files:
        with pd.HDFStore(file, mode='r') as store:
            dfs.append(store[name])
    simAlgoDFs[fe] = pd.concat(dfs)

simAlgoNames = sorted(simAlgoDFs.keys())
if FLAGS.debug:
    print('Input HDF5 keys:')
    print(simAlgoNames)

#########################################################################
################### DATA ANALYSIS: TRIGGER CELLS ########################
#########################################################################
if FLAGS.mode == 'tc':
    if FLAGS.debug:
        subdetvals  = sorted(tcData.subdet.unique())
        layervals  = sorted(tcData.layer.unique())
        etavals  = sorted(tcData[tcNames.eta].unique())
        phivals  = sorted(tcData[tcNames.phi].unique())

        print('Values of Trigger Subdet ({}): {}'.format(len(subdetvals), subdetvals)) #ECAL (1), HCAL silicon (2) and HCAL scintillator (10)
        print('Values of Layers ({}): {}'.format(len(layervals), layervals))
        print('Values of Trigger Eta ({}): {}'.format(len(etavals), etavals))
        print('Values of Trigger Phi ({}): {}'.format(len(phivals), phivals))

    if FLAGS.pos_endcap:
        tcData = tcData[ tcData.zside == 1 ] #only look at positive endcap
        tcData = tcData.drop(['zside'], axis=1)
        tcVariables.remove('zside')

    tcData = tcData[ tcData.subdet == 1 ] #only look at ECAL
    tcData = tcData.drop(['subdet'], axis=1)
    tcVariables.remove('subdet')

    tcData[tcNames.RoverZ] = np.sqrt(tcData.x*tcData.x + tcData.y*tcData.y) / abs(tcData.z)
    #the following cut removes almost no event at all
    tcData = tcData[ (tcData[tcNames.RoverZ] < FLAGS.maxROverZ) & (tcData[tcNames.RoverZ] > FLAGS.minROverZ) ]

    tcData[tcNames.RoverZ] = pd.cut( tcData[tcNames.RoverZ], bins=rzBinEdges, labels=False )
    tcData[tcNames.phi] = pd.cut( tcData[tcNames.phi], bins=phiBinEdges, labels=False )

    ledges = [0,9,10,28]
    ledgeszip = tuple(zip(ledges[:-1],ledges[1:]))
    tcSelections = ['layer>{}, layer<={}'.format(x,y) for x,y in ledgeszip]
    groups = []
    for lmin,lmax in ledgeszip:
        groups.append( tcData[ (tcData.layer>lmin) & (tcData.layer<=lmax) ] )
        groupby = groups[-1].groupby([tcNames.RoverZ, tcNames.phi], as_index=False)
        groups[-1] = groupby.count()
        eta_mins = groupby.min()[tcNames.eta]
        eta_maxs = groupby.max()[tcNames.eta]
        groups[-1].insert(0, tcNames.min_eta, eta_mins)
        groups[-1].insert(0, tcNames.max_eta, eta_maxs)
        groups[-1] = groups[-1].rename(columns={'z': tcNames.nhits})
        groups[-1] = groups[-1][[tcNames.phi, tcNames.nhits, tcNames.RoverZ, tcNames.min_eta, tcNames.max_eta]]

#########################################################################
################### DATA ANALYSIS: SIMULATION ###########################
#########################################################################
if FLAGS.mode == 'sim':
    grid = []
    enrescuts = [-0.35]
    assert(len(enrescuts)==len(fes))
    for i,(fe,cut) in enumerate(zip(fes,enrescuts)):
        df = simAlgoDFs[fe]
        #print(df.groupby("event").filter(lambda x: len(x) > 1))

        if FLAGS.debug:
            print('Cluster level information:')
            print(df.filter(regex='cl3d_*.'))

        df = df[ (df['genpart_exeta']>1.7) & (df['genpart_exeta']<2.8) ]
        df = df[ df[simNames.eta3d]>0 ]
        df['enres'] = ( df['cl3d_energy']-df['genpart_energy'] ) / df['genpart_energy']

        #### Energy resolution histogram ######################################################################
        hist, edges = np.histogram(df['enres'], density=True, bins=300)
        p = figure(width=1800, height=800, title='Energy Resolution: ' + fe)
        p.quad(top=hist, bottom=0, left=edges[:-1], right=edges[1:],
               fill_color="navy", line_color="white", alpha=0.7)
        p.line(x=[cut,cut], y=[0,max(hist)], line_color="#ff8888", line_width=4, alpha=0.9, legend_label="Cut")
        grid.append(p)
        ######################################################################################################
        
        nansel = pd.isna(df['enres']) 
        nandf = df[nansel]
        nandf['enres'] = 1.1
        df = df[~nansel]
        df = pd.concat([df,nandf], sort=False)

        # select events with splitted clusters
        splittedClusters = df[ df['enres'] < cut ]

        # random pick some events (fixing the seed for reproducibility)
        _events_remaining = list(splittedClusters.index.unique())
        _events_sample = random.sample(_events_remaining, NEVENTS)
        splittedClusters = splittedClusters.loc[_events_sample]
        #splittedClusters.sample(n=NEVENTS, replace=False, random_state=8)

        if FLAGS.debug:
            print('SplitClusters Dataset: event random selection')
            print(splittedClusters)
            print(splittedClusters.columns)

        #splitting remaining data into cluster and tc to avoid tc data duplication
        _cl3d_vars = [x for x in splittedClusters.columns.to_list() if 'tc_' not in x]
        splittedClusters_3d = splittedClusters[_cl3d_vars]
        splittedClusters_3d = splittedClusters_3d.reset_index()
        _tc_vars = [x for x in splittedClusters.columns.to_list() if 'cl3d' not in x]

        #trigger cells info is repeated across clusters in the same event
        splittedClusters_tc = splittedClusters.groupby("event").head(1)[_tc_vars] #first() instead of head(1) also works
        
        _tc_vars = [x for x in _tc_vars if 'tc_' in x]
        splittedClusters_tc = splittedClusters_tc.explode( _tc_vars )
        
        for v in _tc_vars:
            splittedClusters_tc[v] = splittedClusters_tc[v].astype(np.float64)

        splittedClusters_tc[simNames.RoverZ] = np.sqrt(splittedClusters_tc.tc_x*splittedClusters_tc.tc_x + splittedClusters_tc.tc_y*splittedClusters_tc.tc_y)  / abs(splittedClusters_tc.tc_z)
        splittedClusters_tc = splittedClusters_tc[ (splittedClusters_tc[simNames.RoverZ] < FLAGS.maxROverZ) & (splittedClusters_tc[simNames.RoverZ] > FLAGS.minROverZ) ]
        splittedClusters_tc = splittedClusters_tc.reset_index()
        splittedClusters_tc[simNames.RoverZ] = pd.cut( splittedClusters_tc[simNames.RoverZ], bins=rzBinEdges, labels=False )
        splittedClusters_tc[simNames.phitc] = pd.cut( splittedClusters_tc[simNames.phitc], bins=phiBinEdges, labels=False )
        simAlgoPlots[fe] = (splittedClusters_3d, splittedClusters_tc)

    if not FLAGS.debug:
        output_file('energyResolution.html')
        _ncols = 1 if len(grid)==1 else 2
        show( gridplot(grid, ncols=_ncols) )

#########################################################################
################### PLOTTING: TRIGGER CELLS #############################
#########################################################################
if FLAGS.mode == 'tc':
    for idx,grp in enumerate(groups):
        source = ColumnDataSource(grp)

        if FLAGS.log:
            mapper = LogColorMapper(palette=mypalette,
                                    low=grp[tcNames.nhits].min(), high=grp[tcNames.nhits].max())
        else:
            mapper = LinearColorMapper(palette=mypalette,
                                       low=grp[tcNames.nhits].min(), high=grp[tcNames.nhits].max())

        title = title_common + '; {}'.format(tcSelections[idx])
        p = figure(width=1800, height=800, title=title,
                   x_range=Range1d(tcData[tcNames.phi].min()-SHIFTH, tcData[tcNames.phi].max()+SHIFTH),
                   y_range=Range1d(tcData[tcNames.RoverZ].min()-SHIFTV, tcData[tcNames.RoverZ].max().max()+SHIFTV),
                   tools="hover,box_select,box_zoom,undo,redo,reset,save", x_axis_location='below',
                   x_axis_type='linear', y_axis_type='linear',
                   )

        p.rect( x=tcNames.phi, y=tcNames.RoverZ,
                source=source,
                width=BINWIDTH, height=BINWIDTH,
                width_units='data', height_units='data',
                line_color='black', fill_color=transform(tcNames.nhits, mapper)
               )

        color_bar = ColorBar(color_mapper=mapper,
                             ticker= ( LogTicker(desired_num_ticks=len(mypalette))
                                       if FLAGS.log else BasicTicker(desired_num_ticks=int(len(mypalette)/4)) ),
                             formatter=PrintfTickFormatter(format="%d")
                             )
        p.add_layout(color_bar, 'right')

        set_figure_props(p, phiBinCenters, rzBinCenters)
        
        p.hover.tooltips = [
            ("#hits", "@{nhits}"),
            ("min(eta)", "@{min_eta}"),
            ("max(eta)", "@{max_eta}"),
        ]

        if not FLAGS.debug:
            output_file('triggerCellsOccup_sel{}_mode{}.html'.format(idx, FLAGS.mode))
            show(p)

#########################################################################
################### PLOTTING: SIMULATION ################################
#########################################################################
if FLAGS.mode == 'sim':
    tabs = []

    for i,(_k,(df_3d,df_tc)) in enumerate(simAlgoPlots.items()):
        for ev in df_tc['event'].unique():
            ev_tc = df_tc[ df_tc.event == ev ]
            ev_3d = df_3d[ df_3d.event == ev ]
            _simCols_tc = [simNames.entc, 'tc_z', simNames.phitc, simNames.RoverZ,
                           simNames.etagen, simNames.phigen, simNames.etatc, simNames.phi_tc]
            ev_tc = ev_tc.filter(items=_simCols_tc)
            ev_3d['cl3d_Roverz'] = calculateRoverZfromEta(ev_3d[simNames.eta3d])
            ev_3d['gen_Roverz']  = calculateRoverZfromEta(ev_3d[simNames.etagen])

            _cl3d_pos_rz, _cl3d_pos_phi = ev_3d['cl3d_Roverz'].unique(), ev_3d[simNames.phi3d].unique()
            if len(_cl3d_pos_rz) == 1 or len(_cl3d_pos_phi) == 1:  #we should have at least two clusters
                print('WARNING: Only one cluster (event={}, phi={}, eta={})'.format(ev, _cl3d_pos_phi, _cl3d_pos_phi))
            cl3d_pos_rz = [ convertToBinIndex(x, rzBinEdges) for x in _cl3d_pos_rz ]
            cl3d_pos_phi = [ convertToBinIndex(x, phiBinEdges) for x in _cl3d_pos_phi ]

            _gen_pos_rz, _gen_pos_phi = ev_3d['gen_Roverz'].unique(), ev_3d[simNames.phigen].unique()
            assert( len(_gen_pos_rz) == 1 and len(_gen_pos_phi) == 1 )
            gen_pos_rz = convertToBinIndex(_gen_pos_rz[0], rzBinEdges)
            gen_pos_phi = convertToBinIndex(_gen_pos_phi[0], phiBinEdges)

            ev_3d = ev_3d.drop(['cl3d_Roverz', simNames.eta3d, simNames.phi3d], axis=1)

            #CHANGE THE LINE BELOW TO GET A WEIGHTED HISTOGRAM
            groupby = ev_tc.groupby([simNames.RoverZ, simNames.phitc], as_index=False)
            group = groupby.count()

            energy_sum = groupby.sum()[simNames.entc]
            eta_mins = groupby.min()[simNames.etatc]
            eta_maxs = groupby.max()[simNames.etatc]

            group = group.rename(columns={'tc_z': simNames.nhits}, errors='raise')
            group.insert(0, simNames.min_eta, eta_mins)
            group.insert(0, simNames.max_eta, eta_maxs)
            group.insert(0, simNames.sum_en, energy_sum)

            source = ColumnDataSource(group)

            title = title_common + '; Algo: {}'.format(_k)
            p = figure(width=1800, height=800, title=title,
                       x_range=Range1d(0-SHIFTH, len(phiBinEdges)+SHIFTH),
                       y_range=Range1d(0-SHIFTV, len(rzBinEdges)-1+SHIFTV),
                       tools="hover,box_select,box_zoom,reset,save", x_axis_location='below',
                       x_axis_type='linear', y_axis_type='linear',
                       )

            if FLAGS.log:
                mapper = LogColorMapper(palette=mypalette,
                                        low=group[simNames.nhits].min(), high=group[simNames.nhits].max())
            else:
                mapper = LinearColorMapper(palette=mypalette,
                                           low=group[simNames.nhits].min(), high=group[simNames.nhits].max())

            color_bar = ColorBar(color_mapper=mapper,
                                 ticker= ( LogTicker(desired_num_ticks=len(mypalette))
                                           if FLAGS.log else BasicTicker(desired_num_ticks=int(len(mypalette)/4)) ),
                                 formatter=PrintfTickFormatter(format="%d")
                                 )
            p.add_layout(color_bar, 'right')

            p.rect( x=simNames.phitc, y=simNames.RoverZ,
                    source=source,
                    width=BINWIDTH, height=BINWIDTH,
                    width_units='data', height_units='data', line_color='black',
                    #fill_color=transform(simNames.nhits, mapper)
                    fill_color=transform(simNames.sum_en, mapper)
                   )

            cross_options = dict(size=40, angle=3.14159/4, line_width=8)
            p.cross(x=gen_pos_phi, y=gen_pos_rz, color='orange',
                    legend_label='Generated particle position', **cross_options)
            p.cross(x=cl3d_pos_phi, y=cl3d_pos_rz, color='red',
                    legend_label='3D cluster positions', **cross_options)

            set_figure_props(p, phiBinCenters, rzBinCenters)
            tabs.append( Panel(child=p, title='Event {}'.format(ev)) )

    if not FLAGS.debug:
        output_file('triggerCellsOccup_mode{}.html'.format(FLAGS.mode))
        show( Tabs(tabs=tabs) )
