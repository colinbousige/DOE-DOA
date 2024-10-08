import streamlit as st
from ressources.functions import *
import optuna
import pandas as pd
import numpy as np
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.gaussian_process.kernels import RBF
import matplotlib.pyplot as plt
from ressources.functions import about_items
from sklearn.preprocessing import LabelEncoder
from datetime import datetime

st.set_page_config(page_title="New experiments – Bayesian Optimisation",
                   page_icon="📈", layout="wide", menu_items=about_items)

style = read_markdown_file("ressources/style.css")
st.markdown(style, unsafe_allow_html=True)

# # # # # # # # # # # # # # # # # # # # # # # # # # # # # 
# Definition of User Interface
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # 
st.write("""
# New experiments – Bayesian Optimisation
""")



tabs = st.tabs(["Data Loading", "Bayesian Optimization"])

with tabs[0]:
    colos = st.columns([2,3])
    data = colos[0].file_uploader("Upload a CSV file (comma separated values)", type=["csv"],
                help="The data file should contain the factors and the response variable.")
    if data is not None:
        data = pd.read_csv(data)
        left, right = st.columns([3,2])
        cols = data.columns.to_numpy()
        colos[1].dataframe(data, hide_index=True)
        mincol = 1 if 'run_order' in cols else 0
        factors = colos[0].multiselect("Select the **factors** columns:", 
                data.columns, default=cols[mincol:-1])
        # response cannut be a factor, so default are all unselected columns in factor
        available = [col for col in cols if col not in factors]
        response = [colos[0].selectbox("Select the **response** column:", 
                available, index=len(available)-1)]
        if len(response) > 0:
            response = response[0]
        # add option to change type of columns
        dtypesF = data[factors].dtypes
        st.write("""##### Select the type and range of each factor
Except for categorical factors, you can increase the ranges to allow the optimization algorithm to explore values outside the current range of measures.""")
        factor_carac = {factor: [dtypesF[factor], np.min(data[factor]), np.max(data[factor])] for factor in factors}
        type_choice = {'object':0, 'int64':1, 'float64':2}
        colos = st.columns(5)
        colos[1].write("<p style='text-align:center;'><b>Type</b></p>", unsafe_allow_html=True)
        colos[2].write("<p style='text-align:center;'><b>Min</b></p>", unsafe_allow_html=True)
        colos[3].write("<p style='text-align:center;'><b>Max</b></p>", unsafe_allow_html=True)
        for factor in factors:
            colos = st.columns(5)
            colos[0].write(f"<p style='text-align:right;'><b>{factor}</b></p>", unsafe_allow_html=True)
            factype = type_choice[f"{factor_carac[factor][0]}"]
            factor_carac[factor][0] = colos[1].selectbox(f"Type of **{factor}**", 
                ['Categorical', 'Integer', 'Float'], key=f"type_{factor}", index = factype, label_visibility='collapsed')
            if factor_carac[factor][0] == 'Categorical':
                factor_carac[factor][0] = 'object'
            elif factor_carac[factor][0] == 'Integer':
                factor_carac[factor][0] = 'int64'
            else:
                factor_carac[factor][0] = 'float64'
            data[factor] = data[factor].astype(factor_carac[factor][0])
            if factor_carac[factor][0] != 'object':
                factor_carac[factor][1] = colos[2].number_input(f"Min value of **{factor}**",
                    value=factor_carac[factor][1], key=f"min_{factor}", label_visibility='collapsed')
                factor_carac[factor][2] = colos[3].number_input(f"Max value of **{factor}**",
                    value=factor_carac[factor][2], key=f"max_{factor}", label_visibility='collapsed')
        data, encoders, dtypes = encode_data(data, factors)


with tabs[1]:
    if data is not None and len(factors) > 0 and len(response) > 0:
        Nexp = st.sidebar.number_input("Number of experiments", 
                min_value=1, value=1, max_value=100, 
                help="Number of experiments to look for the optimum response.")
        model_selection = st.sidebar.selectbox("Select the model", ["Gaussian Process", "Random Forest"],
                help="""### Select the model to use for the optimization.
- **Gaussian Process:** This model will provide an estimate of the response and its uncertainty. It's recommended for small datasets.
- **Random Forest:** This model will provide an estimate of the response without uncertainty. It's recommended for large datasets.
""")
        samplerchoice = st.sidebar.selectbox("Select the sampler", ["TPE", "NSGAII"], help="""### Select the sampler to use for the optimization.  
- **TPE:** Tree-structured Parzen Estimator. This will tend to explore the parameter space more efficiently (exploitation).
- **NSGAII:** Non-dominated Sorting Genetic Algorithm II. This will tend to explore the parameter space more uniformly (exploration).
""")
        sampler_list = {"TPE": optuna.samplers.TPESampler,
                        "NSGAII": optuna.samplers.NSGAIISampler}
        # fix a parameter value
        fixpar = st.sidebar.multiselect("Fix parameter values", factors,
                help="Select one or more factors whose values you want to fix during optimization.")
        fixparval = [None]*len(fixpar)
        if len(fixpar)>0:
            for i,par in enumerate(fixpar):
                if dtypes[par] == 'object':
                    cases = encoders[par].inverse_transform([round(f) for f in data[par].unique()])
                    fixparval[i] = st.sidebar.selectbox(f"Value of **{par}**", cases, 
                                                        key=f"fixpar{i}")
                    fixparval[i] = encoders[par].transform([fixparval[i]])[0]
                else:
                    fixparval[i] = st.sidebar.number_input(f"Value of **{par}**", 
                                    value=np.mean(data[par]), key=f"fixpar{i}")
        fixedparval = {par: val for par,val in zip(fixpar, fixparval)}
        X = data[factors].values
        y = data[response].values
        # Standardize the input feature
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)
        # Train the model
        if model_selection == "Gaussian Process":
            # kernel = RBF(length_scale_bounds='fixed', length_scale=0.25) 
            model = GaussianProcessRegressor(n_restarts_optimizer=10, 
                                             random_state=12345)
        else:
            model = RandomForestRegressor(n_estimators=200, 
                                          n_jobs=-1, random_state=12345)
        model.fit(X_scaled, y)

        # Objective function to maximize
        def evaluate_objective(X):
            X_pred = scaler.transform(X)
            if model_selection == "Gaussian Process":
                response_pred, _ = model.predict(X_pred, return_std=True)
            else:
                response_pred = model.predict(X_pred)
            return response_pred[0]

        def objective(trial):
            # Search space for parameters
            trials = [None]*len(factors)
            for i,factor in enumerate(factors):
                if dtypes[factor] == 'object':
                    suggestions = data[factor].unique() if factor not in fixpar else [fixedparval[factor]]
                    trials[i] = trial.suggest_categorical(factor, suggestions)
                elif dtypes[factor] == 'int':
                    Min = factor_carac[factor][1] if factor not in fixpar else fixedparval[factor]
                    Max = factor_carac[factor][2] if factor not in fixpar else fixedparval[factor]
                    trials[i] = trial.suggest_int(factor, Min, Max)
                else:
                    Min = factor_carac[factor][1] if factor not in fixpar else fixedparval[factor]
                    Max = factor_carac[factor][2] if factor not in fixpar else fixedparval[factor]
                    trials[i] = trial.suggest_float(factor, Min, Max)
            trials = np.array(trials).reshape(1, -1)
            # Evaluate the objective function
            resp = evaluate_objective(trials)
            return resp

        # Perform Bayesian optimization
        cols = st.columns([1,3])
        direction = cols[0].radio("Select the direction to optimize:", ["Maximize", "Minimize"])
        sampler = sampler_list[samplerchoice]()
        study = optuna.create_study(direction=direction.lower(), sampler=sampler)
        
        study.optimize(objective, n_trials=100, n_jobs=-1)
        
        # Get the best hyperparameters
        res = study.trials_dataframe()
        res = res[res['state']=='COMPLETE']
        res = res.sort_values('value', ascending=False)
        # remove the string 'params_' from the column names
        res.columns = [col.replace('params_', '') for col in res.columns]
        # take the first Nexp best parameters
        if direction == "Maximize":
            best_params = res.head(Nexp)[factors+['value']]
        else:
            best_params = res.tail(Nexp)[factors+['value']]
            # reverse row order
            best_params = best_params.iloc[::-1]
        # rename the value column to the response
        best_params = best_params.rename(columns={'value': f"Expected {response}"})
        
        # best_params = pd.DataFrame(columns=factors+[f"Expected {response}"])
        # for i in range(Nexp):
        #     study.optimize(objective, n_trials=50, n_jobs=-1)
        #     # Get the best hyperparameters
        #     BestPars = study.best_params  
        #     BestVal = study.best_value
        #     # store the best parameters and best value in best_params
        #     best_params.loc[i, factors] = [BestPars[factor] for factor in factors]
        #     best_params.loc[i, f"Expected {response}"] = BestVal

        outdf = best_params.copy()
        # make the output more readable
        for col in outdf.columns:
            outdf[col] = np.round(outdf[col], 2)
        outdf = decode_data(outdf, factors, dtypes, encoders)
        cols[1].write("New parameters to try and expected response:")
        cols[1].dataframe(outdf, hide_index=True)
        
        timestamp = datetime.today().strftime('%Y-%m-%d_%H:%M:%S')
        df_new = outdf.copy()
        df_new['run_order'] = np.arange(1, len(df_new)+1)
        df_new['run_order'] = np.random.permutation(df_new['run_order'])
        colos = df_new.columns.tolist()
        colos = colos[-1:] + colos[:-1]
        df_new = df_new[colos]
        # add an empty "response" column to the design
        df_new['response'] = ''
        outfile = writeout(df_new)
        cols[0].download_button(
            label     = f"Download new Experimental Design with {len(df_new)} runs",
            data      = outfile,
            file_name = f'newDOE_{timestamp}.csv',
            mime      = 'text/csv',
            key       = 'download-csv'
        )

        ncols = np.min([len(factors),4])
        cols = st.columns(int(ncols))
        # data = decode_data(data, factors, dtypes, encoders)
        for i,factor in enumerate(factors):
            fig, ax = plt.subplots()
            Xr = pd.DataFrame(columns=factors)
            for f in factors:
                if f == factor and dtypes[f] != 'object':
                    Xr[f] = np.linspace(factor_carac[f][1], factor_carac[f][2], 50)
                elif f == factor and dtypes[f] == 'object':
                    Xr[f] = np.linspace(0, len(data[factor].unique())-1, 50)
                else:
                    Xr[f] = np.repeat(best_params[f].values[0], 50)
            Xr = Xr.values
            Xr = scaler.transform(Xr)
            if model_selection == "Gaussian Process":
                yp, ys = model.predict(Xr, return_std=True)
            else:
                yp = model.predict(Xr)
                ys = 0
            Xr = scaler.inverse_transform(Xr)
            Xr = pd.DataFrame(Xr, columns=factors)
            Xr = Xr[factor].values.reshape(-1, 1)
            ax.plot(Xr, yp)
            ax.fill_between(Xr[:, 0], yp - ys, yp + ys, alpha=0.1, 
                            color='k', label = "Uncertainty")
            ax.scatter(data[factor], data[response], s=100)
            ax.scatter(best_params[factor], 
                       best_params[f"Expected {response}"], s=200, color='red')
            ax.set_xlabel(factor)
            ax.set_ylabel(response)
            # if factor is categorical, change the xticks to the categories
            if dtypes[factor] == 'object':
                ax.set_xticks(np.arange(len(data[factor].unique())))
                labels = encoders[factor].inverse_transform([round(f) for f in data[factor].unique()])
                ax.set_xticklabels(np.sort(labels))
            fig.tight_layout()
            cols[i%ncols].pyplot(fig)
            
        plt.rcParams.update({'font.size': 22})
        cols = st.columns(len(factors)-1)
        for i,faci in enumerate(factors):
            for j,facj in enumerate(factors):
                if j>i:
                    fig, ax = plt.subplots()
                    ax.scatter(data[facj], data[faci], s=100)
                    ax.scatter(best_params[facj], best_params[faci], s=100, color='red')
                    if dtypes[faci] == 'object':
                        ax.set_yticks(np.arange(len(data[faci].unique())))
                        labels = encoders[faci].inverse_transform([round(f) for f in data[faci].unique()])
                        ax.set_yticklabels(np.sort(labels))
                    else:
                        ax.set_ylabel(faci)
                    if dtypes[facj] == 'object':
                        ax.set_xticks(np.arange(len(data[facj].unique())))
                        labels = encoders[facj].inverse_transform([round(f) for f in data[facj].unique()])
                        ax.set_xticklabels(np.sort(labels))
                    else:
                        ax.set_xlabel(facj)
                    fig.tight_layout()
                    cols[j-1].pyplot(fig)


